using System.Security.Cryptography;
using Microsoft.Extensions.Logging.Abstractions;
using MiresSftpUploader.Core;
using MiresSftpUploader.Test.Support;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class DryRunTests
{
    private string _dir = "";

    [TestInitialize]
    public void Setup() => _dir = Directory.CreateTempSubdirectory("mires-dry-").FullName;

    [TestCleanup]
    public void Cleanup()
    {
        try { Directory.Delete(_dir, recursive: true); } catch (IOException) { }
    }

    private string DbPath => Path.Combine(_dir, "state", "state.db");

    private EngineSettings Settings(ScanConfig? scan = null) => new()
    {
        RemoteRoot = "/upload",
        Destination = "sftp.example:22",
        Retry = new RetrySettings { MaxAttempts = 1, BaseDelay = TimeSpan.Zero, MaxDelay = TimeSpan.Zero },
        State = new StateSettings { AccessGroup = TestAccessGroup.Name, Path = DbPath },
        Scan = scan ?? new ScanConfig(),
    };

    private static Task<RunResult> RunAsync(EngineSettings settings, FakeRemote remote, RunOptions options, IProgress<RunEvent>? progress, TimeProvider time, params ISource[] sources) =>
        new Engine(remote, sources, settings, NullLogger<Engine>.Instance, time)
            .RunAsync(options, progress ?? new Progress<RunEvent>(), CancellationToken.None);

    private static Dictionary<string, string> Snapshot(string directory) =>
        Directory.Exists(directory)
            ? Directory.EnumerateFiles(directory, "*", SearchOption.AllDirectories)
                .ToDictionary(f => Path.GetRelativePath(directory, f), f => Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(f))))
            : [];

    [TestMethod]
    public async Task Dry_run_reports_discovered_ignored_and_too_recent_files_and_uploads_nothing()
    {
        var now = new DateTimeOffset(2026, 6, 1, 12, 0, 0, TimeSpan.Zero);
        var time = new Microsoft.Extensions.Time.Testing.FakeTimeProvider(now);
        var remote = new FakeRemote();
        var source = new FakeSource("scans")
            .Add("new.txt", new byte[] { 1 }, now.AddDays(-1))
            .Add(".DS_Store", new byte[] { 2 }, now.AddDays(-1))
            .Add("fresh.txt", new byte[] { 3 }, now.AddSeconds(-1));
        var events = new List<FileOutcomeChanged>();

        var result = await RunAsync(Settings(new ScanConfig { MinFileAgeSeconds = 60 }), remote, new RunOptions { DryRun = true },
            new CollectingProgress(events), time, source);

        Assert.AreEqual(0, result.ExitCode);
        Assert.AreEqual(1, result.Count(FileOutcome.Pending));
        Assert.AreEqual(1, result.Count(FileOutcome.Ignored));
        Assert.AreEqual(1, result.Count(FileOutcome.Skipped));
        Assert.AreEqual("TooRecent", events.Last(e => e.RelativePath == "fresh.txt").Reason);
        Assert.AreEqual(0, remote.ConnectCount);
        Assert.AreEqual(0, source.OpenCount, "a Dry Run reads no file content");
        Assert.IsEmpty(Snapshot(_dir), "a Dry Run creates neither a database nor a lock");
    }

    [TestMethod]
    public async Task Dry_run_after_a_real_run_shows_unchanged_files_as_Skipped_and_leaves_the_database_untouched()
    {
        var remote = new FakeRemote();
        var source = new FakeSource("scans").Add("a.txt", "alpha").Add("b.txt", "beta");
        var settings = Settings();
        await RunAsync(settings, remote, new RunOptions(), null, TimeProvider.System, source);
        source.Add("c.txt", "gamma");
        source.Remove("b.txt");
        var before = Snapshot(_dir);
        var filesBefore = remote.Files.ToDictionary(f => f.Key, f => f.Value);

        var result = await RunAsync(settings, remote, new RunOptions { DryRun = true }, null, TimeProvider.System, source);

        Assert.AreEqual(1, result.Count(FileOutcome.Skipped), "a.txt is unchanged");
        Assert.AreEqual(1, result.Count(FileOutcome.Pending), "c.txt would be uploaded");
        CollectionAssert.AreEquivalent(before, Snapshot(_dir));
        CollectionAssert.AreEquivalent(filesBefore.Keys, remote.Files.Keys.ToArray());
        Assert.AreEqual(1, UploadState.ReadFiles(DbPath).Count(f => f.RelativePath == "b.txt" && f.Status == "Succeeded"),
            "b.txt vanished but a Dry Run does not mark it Missing");
    }

    [TestMethod]
    public async Task Dry_run_works_while_another_Run_holds_the_lock()
    {
        Directory.CreateDirectory(Path.GetDirectoryName(DbPath)!);
        using (new FileStream(DbPath + ".lock", FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None))
        {
            var source = new FakeSource("scans").Add("a.txt", "alpha");

            var result = await RunAsync(Settings(), new FakeRemote(), new RunOptions { DryRun = true }, null, TimeProvider.System, source);

            Assert.AreEqual(0, result.ExitCode);
            Assert.AreEqual(1, result.Count(FileOutcome.Pending));
        }
    }

    private sealed class CollectingProgress(List<FileOutcomeChanged> sink) : IProgress<RunEvent>
    {
        public void Report(RunEvent value)
        {
            if (value is FileOutcomeChanged c) lock (sink) sink.Add(c);
        }
    }
}

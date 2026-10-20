using Microsoft.Extensions.Logging.Abstractions;
using MiresSftpUploader.Core;
using MiresSftpUploader.Test.Support;

namespace MiresSftpUploader.Test.Unit;

/// <summary>An S3 Source identifies a file version by size and ETag (its modified time is only used for Scan min-age).</summary>
[TestClass]
public sealed class ETagChangeDetectionTests
{
    private string _dir = "";
    private static readonly DateTimeOffset Stamp = new(2026, 3, 3, 0, 0, 0, TimeSpan.Zero);

    [TestInitialize]
    public void Setup() => _dir = Directory.CreateTempSubdirectory("mires-etag-").FullName;

    [TestCleanup]
    public void Cleanup()
    {
        try { Directory.Delete(_dir, recursive: true); } catch (IOException) { }
    }

    private EngineSettings Settings(params ArchiveRuleConfig[] rules) => new()
    {
        RemoteRoot = "/upload",
        Destination = "sftp.example:22",
        Retry = new RetrySettings { MaxAttempts = 1, BaseDelay = TimeSpan.Zero, MaxDelay = TimeSpan.Zero },
        State = new StateSettings { Path = Path.Combine(_dir, "state.db") },
        Archive = new ArchiveConfig { StagingPath = Path.Combine(_dir, "staging"), Rules = rules },
    };

    private static Task<RunResult> Run(EngineSettings settings, FakeRemote remote, FakeSource source, IProgress<RunEvent>? progress = null) =>
        new Engine(remote, [source], settings, NullLogger<Engine>.Instance, TimeProvider.System)
            .RunAsync(new RunOptions(), progress ?? new Progress<RunEvent>(), CancellationToken.None);

    [TestMethod]
    public async Task A_file_with_the_same_size_and_ETag_is_skipped_even_when_its_modified_time_moved()
    {
        var remote = new FakeRemote();
        var source = new FakeSource("bucket").Add("a.txt", "alpha", Stamp, etag: "e1");
        await Run(Settings(), remote, source);

        source.Add("a.txt", "alpha", Stamp.AddDays(1), etag: "e1");
        var second = await Run(Settings(), remote, source);

        Assert.AreEqual(1, second.Count(FileOutcome.Skipped));
        Assert.AreEqual(0, second.Count(FileOutcome.Succeeded));
    }

    [TestMethod]
    public async Task A_file_with_the_same_size_and_modified_time_but_a_new_ETag_is_uploaded_again()
    {
        var remote = new FakeRemote();
        var source = new FakeSource("bucket").Add("a.txt", "alpha", Stamp, etag: "e1");
        await Run(Settings(), remote, source);

        source.Add("a.txt", "omega", Stamp, etag: "e2");
        var second = await Run(Settings(), remote, source);

        Assert.AreEqual(1, second.Count(FileOutcome.Succeeded));
        Assert.AreEqual("omega", remote.ReadText("/upload/bucket/a.txt"));
    }

    [TestMethod]
    public async Task An_Archive_member_whose_ETag_changes_while_it_is_read_fails_with_ChangedDuringArchive()
    {
        var remote = new FakeRemote();
        var source = new FakeSource("bucket").Add("d/a.jpg", "alpha", Stamp, etag: "e1");
        source.AfterOpen = _ => source.Add("d/a.jpg", "omega", Stamp, etag: "e2");
        var seen = new List<RunEvent>();

        var result = await Run(Settings(new ArchiveRuleConfig { Name = "tiles", Pattern = @"\.jpg$" }), remote, source, new SyncProgress(seen.Add));

        Assert.AreEqual(1, result.ExitCode);
        var failure = seen.OfType<FileOutcomeChanged>().Last(e => e.RelativePath == "d/a.jpg");
        StringAssert.Contains(failure.Reason, "ChangedDuringArchive");
    }

    private sealed class SyncProgress(Action<RunEvent> onReport) : IProgress<RunEvent>
    {
        public void Report(RunEvent value) => onReport(value);
    }
}

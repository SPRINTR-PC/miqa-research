using System.Text.Json;
using Microsoft.Extensions.Logging.Abstractions;
using MiresSftpUploader.Core;
using MiresSftpUploader.Test.Support;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class RetryTests
{
    private string _dir = "";

    [TestInitialize]
    public void Setup() => _dir = Directory.CreateTempSubdirectory("mires-retry-").FullName;

    [TestCleanup]
    public void Cleanup()
    {
        try { Directory.Delete(_dir, recursive: true); } catch (IOException) { }
    }

    private string DbPath => Path.Combine(_dir, "state.db");

    private EngineSettings Settings(string? statePath = "") => new()
    {
        RemoteRoot = "/upload",
        Destination = "sftp.example:22",
        Retry = new RetrySettings { MaxAttempts = 1, BaseDelay = TimeSpan.Zero, MaxDelay = TimeSpan.Zero },
        State = new StateSettings { Path = statePath == "" ? DbPath : statePath },
    };

    private static Task<RunResult> Run(EngineSettings settings, FakeRemote remote, FakeSource source, RunOptions? options = null) =>
        new Engine(remote, [source], settings, NullLogger<Engine>.Instance, TimeProvider.System)
            .RunAsync(options ?? new RunOptions(), new Progress<RunEvent>(), CancellationToken.None);

    /// <summary>A first Run in which b.txt and c.txt fail while a.txt succeeds.</summary>
    private async Task<(RunResult First, FakeRemote Remote, FakeSource Source)> FirstRunWithTwoFailures()
    {
        var remote = new FakeRemote();
        var source = new FakeSource("scans").Add("a.txt", "alpha").Add("b.txt", "beta").Add("c.txt", "gamma").Add("d.txt", "delta");
        remote.Inject(RemoteOperation.Upload, RemoteResult.Failed("disk full"), pathContains: "b.txt");
        remote.Inject(RemoteOperation.Upload, RemoteResult.Failed("disk full"), pathContains: "c.txt");
        var first = await Run(Settings(), remote, source);
        Assert.AreEqual(1, first.ExitCode);
        return (first, remote, source);
    }

    [TestMethod]
    public async Task Retry_uploads_only_the_failed_files_without_scanning_the_source()
    {
        var (first, remote, source) = await FirstRunWithTwoFailures();
        var listings = source.ListCount;
        var opens = source.OpenCount;

        var retry = await Run(Settings(), remote, source, new RunOptions { RetryOf = first.RunId });

        Assert.AreEqual(0, retry.ExitCode);
        Assert.AreEqual(2, retry.Count(FileOutcome.Succeeded));
        Assert.AreEqual(0, retry.Count(FileOutcome.Skipped));
        Assert.AreEqual(listings, source.ListCount, "a retry does not rescan");
        Assert.AreEqual(opens + 2, source.OpenCount, "only the failed files are read");
        Assert.AreEqual("beta", remote.ReadText("/upload/scans/b.txt"));
        Assert.AreEqual("gamma", remote.ReadText("/upload/scans/c.txt"));
        Assert.IsTrue(UploadState.ReadFiles(DbPath).All(f => f.Status == "Succeeded"));
    }

    [TestMethod]
    public async Task Retry_is_recorded_as_a_retry_run_and_its_manifest_still_lists_every_delivered_file()
    {
        var (first, remote, source) = await FirstRunWithTwoFailures();

        var retry = await Run(Settings(), remote, source, new RunOptions { RetryOf = first.RunId });

        Assert.AreEqual("Retry", new RunHistory(Settings().State, TimeProvider.System).GetRun(retry.RunId)!.Summary.Mode);
        using var manifest = JsonDocument.Parse(remote.ReadText("/upload/scans/manifest.json"));
        Assert.IsTrue(manifest.RootElement.GetProperty("complete").GetBoolean());
        CollectionAssert.AreEqual(new[] { "a.txt", "b.txt", "c.txt", "d.txt" },
            manifest.RootElement.GetProperty("members").EnumerateArray().Select(f => f.GetProperty("path").GetString()).ToArray());
        Assert.AreEqual(0, retry.Count(FileOutcome.Skipped), "carried-over files are not counted as this Run's outcomes");
    }

    [TestMethod]
    public async Task A_file_that_vanished_since_is_missing_and_not_an_error()
    {
        var (first, remote, source) = await FirstRunWithTwoFailures();
        source.Remove("b.txt");

        var retry = await Run(Settings(), remote, source, new RunOptions { RetryOf = first.RunId });

        Assert.AreEqual(0, retry.ExitCode);
        Assert.AreEqual(1, retry.Count(FileOutcome.Succeeded));
        Assert.AreEqual(1, retry.Count(FileOutcome.Skipped));
        Assert.AreEqual("Missing", UploadState.ReadFiles(DbPath).Single(f => f.RelativePath == "b.txt").Status);
        var detail = new RunHistory(Settings().State, TimeProvider.System).GetRun(retry.RunId)!;
        Assert.AreEqual("Missing", detail.Files.Single(f => f.RelativePath == "b.txt").Reason);
    }

    [TestMethod]
    public async Task A_file_that_failed_again_stays_failed_with_exit_1()
    {
        var (first, remote, source) = await FirstRunWithTwoFailures();
        remote.Inject(RemoteOperation.Upload, RemoteResult.Failed("still full"), pathContains: "c.txt");

        var retry = await Run(Settings(), remote, source, new RunOptions { RetryOf = first.RunId });

        Assert.AreEqual(1, retry.ExitCode);
        Assert.AreEqual(1, retry.Count(FileOutcome.Succeeded));
        Assert.AreEqual(1, retry.Count(FileOutcome.Failed));
    }

    [TestMethod]
    public async Task A_file_that_a_later_run_already_delivered_is_not_uploaded_again()
    {
        var (first, remote, source) = await FirstRunWithTwoFailures();
        await Run(Settings(), remote, source);
        var opens = source.OpenCount;

        var retry = await Run(Settings(), remote, source, new RunOptions { RetryOf = first.RunId });

        Assert.AreEqual(0, retry.ExitCode);
        Assert.AreEqual(0, retry.Count(FileOutcome.Succeeded));
        Assert.AreEqual(opens, source.OpenCount);
    }

    [TestMethod]
    public async Task Retry_of_an_unknown_run_exits_2()
    {
        await FirstRunWithTwoFailures();

        var retry = await Run(Settings(), new FakeRemote(), new FakeSource("scans"), new RunOptions { RetryOf = Guid.NewGuid() });

        Assert.AreEqual(2, retry.ExitCode);
        StringAssert.Contains(retry.Reason, "Run");
    }

    [TestMethod]
    public async Task Retry_without_an_upload_state_exits_2()
    {
        var retry = await Run(Settings(statePath: null), new FakeRemote(), new FakeSource("scans"), new RunOptions { RetryOf = Guid.NewGuid() });

        Assert.AreEqual(2, retry.ExitCode);
    }
}

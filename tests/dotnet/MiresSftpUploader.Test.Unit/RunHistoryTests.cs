using Microsoft.Extensions.Logging.Abstractions;
using MiresSftpUploader.Core;
using MiresSftpUploader.Test.Support;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class RunHistoryTests
{
    private string _dir = "";

    [TestInitialize]
    public void Setup() => _dir = Directory.CreateTempSubdirectory("mires-history-").FullName;

    [TestCleanup]
    public void Cleanup()
    {
        try { Directory.Delete(_dir, recursive: true); } catch (IOException) { }
    }

    private string DbPath => Path.Combine(_dir, "state.db");

    private EngineSettings Settings() => new()
    {
        RemoteRoot = "/upload",
        Destination = "sftp.example:22",
        Retry = new RetrySettings { MaxAttempts = 1, BaseDelay = TimeSpan.Zero, MaxDelay = TimeSpan.Zero },
        State = new StateSettings { Path = DbPath, CancelPollInterval = TimeSpan.FromMilliseconds(20) },
    };

    private Engine NewEngine(FakeRemote remote, ISource source, TimeProvider? time = null, EngineSettings? settings = null) =>
        new(remote, [source], settings ?? Settings(), NullLogger<Engine>.Instance, time ?? TimeProvider.System);

    private static Task<RunResult> Run(Engine engine, RunOptions? options = null) =>
        engine.RunAsync(options ?? new RunOptions(), new Progress<RunEvent>(), CancellationToken.None);

    private RunHistory History(TimeProvider? time = null) => new(Settings().State, time ?? TimeProvider.System);

    /// <summary>One clean Run followed by one Run with a failed file.</summary>
    private async Task<(RunResult Clean, RunResult Failing, FakeRemote Remote, FakeSource Source)> TwoRuns()
    {
        var remote = new FakeRemote();
        var source = new FakeSource("scans").Add("a.txt", "alpha");
        var clean = await Run(NewEngine(remote, source), new RunOptions { StartedBy = "anna" });
        source.Add("b.txt", "beta");
        remote.Inject(RemoteOperation.Upload, RemoteResult.Failed("disk full"), times: 5, pathContains: "b.txt");
        var failing = await Run(NewEngine(remote, source), new RunOptions { StartedBy = "bo" });
        return (clean, failing, remote, source);
    }

    [TestMethod]
    public async Task List_runs_returns_newest_first_with_who_status_exit_code_and_counts()
    {
        var (clean, failing, _, _) = await TwoRuns();

        var runs = History().ListRuns();

        CollectionAssert.AreEqual(new[] { failing.RunId, clean.RunId }, runs.Select(r => r.RunId).ToArray());
        Assert.AreEqual("bo", runs[0].StartedBy);
        Assert.AreEqual("Finished", runs[0].Status);
        Assert.AreEqual(1, runs[0].ExitCode);
        Assert.AreEqual(1, runs[0].Counts["Failed"]);
        Assert.AreEqual(1, runs[0].Counts["Skipped"]);
        Assert.AreEqual(0, runs[1].ExitCode);
    }

    [TestMethod]
    public async Task List_runs_filters_by_needs_attention_and_limit()
    {
        var (_, failing, _, _) = await TwoRuns();

        var attention = History().ListRuns(new RunFilter { Kind = RunFilterKind.NeedsAttention });
        var limited = History().ListRuns(new RunFilter { Limit = 1 });

        CollectionAssert.AreEqual(new[] { failing.RunId }, attention.Select(r => r.RunId).ToArray());
        Assert.HasCount(1, limited);
        Assert.AreEqual(failing.RunId, limited[0].RunId);
    }

    [TestMethod]
    public async Task Get_run_returns_the_outcome_of_every_file_or_null_for_an_unknown_run()
    {
        var (_, failing, _, _) = await TwoRuns();

        var detail = History().GetRun(failing.RunId);

        Assert.IsNotNull(detail);
        Assert.AreEqual("Failed", detail.Files.Single(f => f.RelativePath == "b.txt").Outcome);
        StringAssert.Contains(detail.Files.Single(f => f.RelativePath == "b.txt").Reason, "disk full");
        Assert.AreEqual("Skipped", detail.Files.Single(f => f.RelativePath == "a.txt").Outcome);
        Assert.IsNull(History().GetRun(Guid.NewGuid()));
    }

    [TestMethod]
    public async Task Another_account_can_cancel_a_live_run_which_ends_with_exit_130()
    {
        var remote = new FakeRemote();
        var stuck = new StuckSource("scans");
        var running = Run(NewEngine(remote, stuck), new RunOptions { StartedBy = "anna" });
        await stuck.Opened.Task.WaitAsync(TimeSpan.FromSeconds(10));
        var history = History();
        var live = history.ListRuns(new RunFilter { Kind = RunFilterKind.Live }).Single();

        Assert.IsTrue(history.RequestCancel(live.RunId));
        var result = await running.WaitAsync(TimeSpan.FromSeconds(10));

        Assert.AreEqual(130, result.ExitCode);
        var after = history.GetRun(live.RunId)!.Summary;
        Assert.AreEqual("Finished", after.Status);
        Assert.AreEqual(130, after.ExitCode);
        Assert.IsTrue(after.CancelRequested);
    }

    [TestMethod]
    public async Task Cancel_request_for_a_run_that_is_not_live_is_refused()
    {
        var (clean, _, _, _) = await TwoRuns();

        Assert.IsFalse(History().RequestCancel(clean.RunId));
        Assert.IsFalse(History().RequestCancel(Guid.NewGuid()));
    }

    [TestMethod]
    public async Task Sweep_marks_a_run_with_a_stale_heartbeat_abandoned_and_leaves_fresh_ones()
    {
        var time = new Microsoft.Extensions.Time.Testing.FakeTimeProvider(new DateTimeOffset(2026, 3, 1, 12, 0, 0, TimeSpan.Zero));
        var remote = new FakeRemote();
        await Assert.ThrowsAsync<InvalidOperationException>(() => Run(NewEngine(remote, new CrashingSource("scans", "a.txt"), time)));
        var history = History(time);

        time.Advance(TimeSpan.FromSeconds(30));
        Assert.AreEqual(0, history.SweepAbandoned());
        time.Advance(TimeSpan.FromSeconds(31));
        Assert.AreEqual(1, history.SweepAbandoned());

        Assert.AreEqual("Abandoned", history.ListRuns().Single().Status);
        Assert.AreEqual("Failed", UploadState.ReadFiles(DbPath).Single().Status, "the in-flight file is retried by the next Run");
    }

    [TestMethod]
    public async Task A_sweep_by_the_history_does_not_stop_the_next_run_cleaning_the_part_file()
    {
        var time = new Microsoft.Extensions.Time.Testing.FakeTimeProvider(new DateTimeOffset(2026, 3, 1, 12, 0, 0, TimeSpan.Zero));
        var remote = new FakeRemote();
        await Assert.ThrowsAsync<InvalidOperationException>(() => Run(NewEngine(remote, new CrashingSource("scans", "a.txt"), time)));
        await using (var session = (await remote.ConnectAsync(default)).Value!)
        {
            await session.EnsureDirectoryAsync("/upload/scans", default);
            await session.UploadAsync(new MemoryStream("half"u8.ToArray()), "/upload/scans/a.txt.part", default);
        }
        time.Advance(TimeSpan.FromSeconds(61));
        History(time).SweepAbandoned();

        var result = await Run(NewEngine(remote, new FakeSource("scans").Add("a.txt", "alpha"), time));

        Assert.AreEqual(0, result.ExitCode);
        Assert.IsFalse(remote.Files.ContainsKey("/upload/scans/a.txt.part"));
        Assert.AreEqual("alpha", remote.ReadText("/upload/scans/a.txt"));
    }

    [TestMethod]
    public void List_runs_on_a_missing_database_is_empty()
    {
        Assert.IsEmpty(History().ListRuns());
        Assert.IsFalse(File.Exists(DbPath), "reading must not create the database");
    }

    /// <summary>Lists one file and blocks when it is opened until the Run is cancelled.</summary>
    private sealed class StuckSource(string name) : ISource
    {
        public TaskCompletionSource Opened { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public string Name { get; } = name;
        public string? RemotePath => null;

        public async IAsyncEnumerable<SourceFile> ListAsync([System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken cancellationToken)
        {
            await Task.Yield();
            yield return new SourceFile("a.txt", 5, new DateTimeOffset(2026, 1, 1, 0, 0, 0, TimeSpan.Zero));
        }

        public async Task<Stream> OpenReadAsync(string relativePath, CancellationToken cancellationToken)
        {
            Opened.TrySetResult();
            await Task.Delay(Timeout.Infinite, cancellationToken);
            throw new InvalidOperationException("unreachable");
        }
    }

    /// <summary>Lists one file and throws a non-I/O exception when it is opened, as if the process died mid-upload.</summary>
    private sealed class CrashingSource(string name, string file) : ISource
    {
        public string Name { get; } = name;
        public string? RemotePath => null;

        public async IAsyncEnumerable<SourceFile> ListAsync([System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken cancellationToken)
        {
            await Task.Yield();
            yield return new SourceFile(file, 5, new DateTimeOffset(2026, 1, 1, 0, 0, 0, TimeSpan.Zero));
        }

        public Task<Stream> OpenReadAsync(string relativePath, CancellationToken cancellationToken) =>
            throw new InvalidOperationException("simulated crash");
    }
}

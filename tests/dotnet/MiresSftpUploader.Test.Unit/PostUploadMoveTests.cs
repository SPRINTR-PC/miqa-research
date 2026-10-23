using Microsoft.Extensions.Logging.Abstractions;
using MiresSftpUploader.Core;
using MiresSftpUploader.Test.Support;

namespace MiresSftpUploader.Test.Unit;

/// <summary>Post-upload Move through the Engine, with an in-memory Source and remote and a real Upload State.</summary>
[TestClass]
public sealed class PostUploadMoveTests
{
    private string _dir = "";

    [TestInitialize]
    public void Setup() => _dir = Directory.CreateTempSubdirectory("mires-move-").FullName;

    [TestCleanup]
    public void Cleanup()
    {
        try { Directory.Delete(_dir, recursive: true); } catch (IOException) { }
    }

    private string DbPath => Path.Combine(_dir, "data", "state.db");

    private static readonly MoveTargetConfig Done = new() { Action = MoveAction.Move, Path = "/done" };
    private static readonly MoveTargetConfig Failed = new() { Action = MoveAction.Move, Path = "/failed" };

    private EngineSettings Settings(
        MoveTargetConfig? onSuccess = null, MoveTargetConfig? onFailure = null, bool moveFailuresAreErrors = false,
        ScanConfig? scan = null, IReadOnlyList<ArchiveRuleConfig>? rules = null) => new()
    {
        RemoteRoot = "/upload",
        Destination = "sftp.example:22",
        Retry = new RetrySettings { MaxAttempts = 1, BaseDelay = TimeSpan.Zero, MaxDelay = TimeSpan.Zero },
        State = new StateSettings { AccessGroup = TestAccessGroup.Name, Path = DbPath },
        Scan = scan ?? new ScanConfig(),
        MoveFailuresAreErrors = moveFailuresAreErrors,
        Archive = new ArchiveConfig { StagingPath = Path.Combine(_dir, "staging"), MinFreeSpaceBytes = 0, Rules = rules ?? [] },
        SourceConfigs =
        [
            new SourceConfig
            {
                Name = "scans",
                AfterUpload = new AfterUploadConfig { OnSuccess = onSuccess ?? new MoveTargetConfig(), OnFailure = onFailure ?? new MoveTargetConfig() },
            },
        ],
    };

    private static FakeSource NewSource() =>
        new FakeSource("scans").Add("a.txt", [1]).Add("sub/b.txt", [2, 2]);

    private sealed class Events : IProgress<RunEvent>
    {
        public List<RunEvent> All { get; } = [];
        public void Report(RunEvent value) { lock (All) All.Add(value); }
        public IEnumerable<string> Warnings => All.OfType<RunWarning>().Select(w => w.Message);
    }

    private static Task<RunResult> RunAsync(EngineSettings settings, FakeRemote remote, ISource source, RunOptions? options = null, Events? events = null, TimeProvider? time = null) =>
        new Engine(remote, [source], settings, NullLogger<Engine>.Instance, time ?? TimeProvider.System)
            .RunAsync(options ?? new RunOptions(), events ?? new Events(), CancellationToken.None);

    private string StatusOf(string path) => UploadState.ReadFiles(DbPath).Single(f => f.RelativePath == path).Status;

    [TestMethod]
    public async Task Uploaded_files_move_to_the_success_target_keeping_their_relative_path_and_are_recorded_as_MovedAway()
    {
        var source = NewSource();

        var result = await RunAsync(Settings(onSuccess: Done), new FakeRemote(), source);

        Assert.AreEqual(ExitCodes.Ok, result.ExitCode);
        CollectionAssert.AreEquivalent(new[] { "a.txt", "sub/b.txt" }, source.MovedPaths);
        CollectionAssert.AreEqual(new byte[] { 2, 2 }, source.MovedFile(Done, "sub/b.txt"));
        Assert.AreEqual(2, result.MovedAway);
        Assert.AreEqual("MovedAway", StatusOf("a.txt"));
    }

    [TestMethod]
    public async Task Directory_Source_files_move_on_disk_to_the_success_and_failure_directories()
    {
        var inbox = Directory.CreateDirectory(Path.Combine(_dir, "inbox")).FullName;
        Directory.CreateDirectory(Path.Combine(inbox, "sub"));
        File.WriteAllText(Path.Combine(inbox, "good.txt"), "good");
        File.WriteAllText(Path.Combine(inbox, "sub", "bad.txt"), "bad");
        var done = Path.Combine(_dir, "done");
        var failed = Path.Combine(_dir, "failed");
        var remote = new FakeRemote();
        remote.Inject(RemoteOperation.Upload, RemoteResult.Failed("boom"), times: 10, pathContains: "bad.txt");
        var settings = Settings(
            onSuccess: new MoveTargetConfig { Action = MoveAction.Move, Path = done },
            onFailure: new MoveTargetConfig { Action = MoveAction.Move, Path = failed });

        var result = await RunAsync(settings, remote, new DirectorySource("scans", inbox));

        Assert.AreEqual(ExitCodes.SomeFilesFailed, result.ExitCode);
        Assert.AreEqual("good", File.ReadAllText(Path.Combine(done, "good.txt")));
        Assert.AreEqual("bad", File.ReadAllText(Path.Combine(failed, "sub", "bad.txt")));
        Assert.IsEmpty(Directory.GetFiles(inbox, "*", SearchOption.AllDirectories));
    }

    [TestMethod]
    public async Task A_moved_file_is_not_Missing_on_the_next_Run_and_is_not_uploaded_again()
    {
        var source = NewSource();
        var remote = new FakeRemote();
        var settings = Settings(onSuccess: Done);
        await RunAsync(settings, remote, source);

        var second = await RunAsync(settings, remote, source);

        Assert.AreEqual(0, second.Count(FileOutcome.Succeeded));
        Assert.AreEqual("MovedAway", StatusOf("a.txt"));
        Assert.AreEqual("MovedAway", StatusOf("sub/b.txt"));
    }

    [TestMethod]
    public async Task The_Manifest_still_lists_a_file_that_was_moved_away()
    {
        var remote = new FakeRemote();

        var source = NewSource();
        var settings = Settings(onSuccess: Done);
        await RunAsync(settings, remote, source);
        await RunAsync(settings, remote, source);

        var manifest = remote.ReadText("/upload/scans/manifest.json");
        StringAssert.Contains(manifest, "sub/b.txt");
        Assert.DoesNotContain("missingAtSource", manifest);
    }

    [TestMethod]
    public async Task A_retry_Manifest_still_lists_files_moved_away_by_the_Run_it_retries()
    {
        var source = NewSource();
        var remote = new FakeRemote();
        remote.Inject(RemoteOperation.Upload, RemoteResult.Failed("boom"), times: 1, pathContains: "sub/b.txt");
        var settings = Settings(onSuccess: Done);
        var first = await RunAsync(settings, remote, source);

        await RunAsync(settings, remote, source, new RunOptions { RetryOf = first.RunId });

        var manifest = remote.ReadText("/upload/scans/manifest.json");
        StringAssert.Contains(manifest, "a.txt");
        StringAssert.Contains(manifest, "sub/b.txt");
    }

    [TestMethod]
    public async Task Without_a_Move_configured_nothing_moves()
    {
        var source = NewSource();

        var result = await RunAsync(Settings(), new FakeRemote(), source);

        Assert.IsEmpty(source.MovedPaths);
        Assert.AreEqual(0, result.MovedAway);
        Assert.AreEqual("Succeeded", StatusOf("a.txt"));
    }

    [TestMethod]
    public async Task Unchanged_files_that_were_Skipped_move_too()
    {
        var source = NewSource();
        var remote = new FakeRemote();
        await RunAsync(Settings(), remote, source);

        var second = await RunAsync(Settings(onSuccess: Done), remote, source);

        Assert.AreEqual(2, second.Count(FileOutcome.Skipped));
        Assert.AreEqual(2, source.MovedPaths.Count);
    }

    [TestMethod]
    public async Task A_Failed_file_moves_to_the_failure_target_and_the_others_to_the_success_target()
    {
        var source = NewSource();
        var remote = new FakeRemote();
        remote.Inject(RemoteOperation.Upload, RemoteResult.Failed("boom"), times: 10, pathContains: "sub/b.txt");

        var result = await RunAsync(Settings(onSuccess: Done, onFailure: Failed), remote, source);

        Assert.AreEqual(ExitCodes.SomeFilesFailed, result.ExitCode);
        Assert.IsNotNull(source.MovedFile(Done, "a.txt"));
        Assert.IsNotNull(source.MovedFile(Failed, "sub/b.txt"));
        Assert.IsNull(source.MovedFile(Done, "sub/b.txt"));
    }

    [TestMethod]
    public async Task A_file_that_changed_during_upload_is_Failed_and_not_moved()
    {
        var source = NewSource();
        source.AfterOpen = path =>
        {
            if (path == "a.txt") source.Add("a.txt", [7, 7, 7], new DateTimeOffset(2026, 2, 2, 0, 0, 0, TimeSpan.Zero));
        };

        var result = await RunAsync(Settings(onSuccess: Done, onFailure: Failed), new FakeRemote(), source);

        Assert.AreEqual(1, result.Count(FileOutcome.Failed));
        CollectionAssert.AreEqual(new[] { "sub/b.txt" }, source.MovedPaths);
        Assert.IsNull(source.MovedFile(Failed, "a.txt"));
    }

    [TestMethod]
    public async Task Ignored_and_Too_Recent_files_never_move()
    {
        var now = new DateTimeOffset(2026, 6, 1, 12, 0, 0, TimeSpan.Zero);
        var source = new FakeSource("scans")
            .Add("ok.txt", [1], now.AddDays(-1))
            .Add(".DS_Store", [2], now.AddDays(-1))
            .Add("fresh.txt", [3], now.AddSeconds(-1));
        var time = new Microsoft.Extensions.Time.Testing.FakeTimeProvider(now);

        await RunAsync(Settings(onSuccess: Done, onFailure: Failed, scan: new ScanConfig { MinFileAgeSeconds = 60 }), new FakeRemote(), source, time: time);

        CollectionAssert.AreEqual(new[] { "ok.txt" }, source.MovedPaths);
    }

    [TestMethod]
    public async Task A_Dry_Run_never_moves()
    {
        var source = NewSource();

        await RunAsync(Settings(onSuccess: Done, onFailure: Failed), new FakeRemote(), source, new RunOptions { DryRun = true });

        Assert.IsEmpty(source.MovedPaths);
    }

    [TestMethod]
    public async Task A_move_happens_only_after_the_outcome_is_committed_to_the_Upload_State()
    {
        var source = NewSource();
        var statusWhenMoved = new Dictionary<string, string>();
        source.MoveInterceptor = path =>
        {
            statusWhenMoved[path] = UploadState.ReadFiles(DbPath).SingleOrDefault(f => f.RelativePath == path)?.Status ?? "none";
            return null;
        };

        await RunAsync(Settings(onSuccess: Done), new FakeRemote(), source);

        Assert.AreEqual("Succeeded", statusWhenMoved["a.txt"]);
        Assert.AreEqual("Succeeded", statusWhenMoved["sub/b.txt"]);
    }

    [TestMethod]
    public async Task An_existing_target_leaves_the_file_in_place_as_a_warning_without_changing_the_upload_outcome()
    {
        var source = NewSource();
        source.PutMoved(Done, "a.txt", [9]);
        var events = new Events();

        var result = await RunAsync(Settings(onSuccess: Done), new FakeRemote(), source, events: events);

        Assert.AreEqual(ExitCodes.Ok, result.ExitCode);
        Assert.AreEqual(2, result.Count(FileOutcome.Succeeded));
        Assert.AreEqual(1, result.MoveFailures);
        Assert.AreEqual(1, result.MovedAway);
        CollectionAssert.AreEqual(new byte[] { 9 }, source.MovedFile(Done, "a.txt"));
        Assert.IsNotNull(await source.StatAsync("a.txt", CancellationToken.None));
        Assert.AreEqual("Succeeded", StatusOf("a.txt"));
        Assert.IsTrue(events.Warnings.Any(w => w.Contains("MoveTargetExists") && w.Contains("a.txt")));
    }

    [TestMethod]
    public async Task A_failed_move_gives_exit_1_only_with_MoveFailuresAreErrors()
    {
        var failing = NewSource();
        failing.MoveInterceptor = _ => MoveResult.Failed("disk full");
        var lenient = await RunAsync(Settings(onSuccess: Done), new FakeRemote(), failing);

        var strictSource = NewSource();
        strictSource.MoveInterceptor = _ => MoveResult.Failed("disk full");
        var strict = await RunAsync(Settings(onSuccess: Done, moveFailuresAreErrors: true), new FakeRemote(), strictSource);

        Assert.AreEqual(ExitCodes.Ok, lenient.ExitCode);
        Assert.AreEqual(ExitCodes.SomeFilesFailed, strict.ExitCode);
        Assert.AreEqual(2, strict.MoveFailures);
    }

    [TestMethod]
    public async Task A_file_modified_between_upload_and_move_is_not_moved()
    {
        var inner = NewSource();
        var statCalls = 0;
        var source = new ChangingAfterUploadSource(inner, () => statCalls++ >= 1 ? new SourceFile("a.txt", 1, DateTimeOffset.UnixEpoch.AddDays(5)) : null);
        var events = new Events();

        await RunAsync(Settings(onSuccess: Done), new FakeRemote(), source, events: events);

        CollectionAssert.AreEqual(new[] { "sub/b.txt" }, inner.MovedPaths);
        Assert.IsTrue(events.Warnings.Any(w => w.Contains("a.txt") && w.Contains("changed")));
    }

    [TestMethod]
    public async Task Archive_members_move_together_after_the_Archive_is_committed_and_the_Archive_is_MovedAway()
    {
        var source = new FakeSource("scans").Add("d/1.jpg", [1]).Add("d/2.jpg", [2]).Add("keep.txt", [3]);
        var statusWhenMoved = new List<string>();
        source.MoveInterceptor = _ =>
        {
            statusWhenMoved.Add(UploadState.ReadFiles(DbPath).Single(f => f.RelativePath == "d/jpgs.zip").Status);
            return null;
        };
        var rule = new ArchiveRuleConfig { Name = "jpgs", Pattern = @"\.jpg$", ArchiveName = "jpgs.zip" };

        var result = await RunAsync(Settings(onSuccess: Done, rules: [rule]), new FakeRemote(), source);

        Assert.AreEqual(ExitCodes.Ok, result.ExitCode);
        CollectionAssert.AreEquivalent(new[] { "d/1.jpg", "d/2.jpg", "keep.txt" }, source.MovedPaths);
        Assert.IsTrue(statusWhenMoved.Take(2).All(s => s == "Succeeded"), "the first two moves are the members, after the Archive was recorded");
        Assert.AreEqual("MovedAway", StatusOf("d/jpgs.zip"));
    }

    [TestMethod]
    public async Task Members_of_an_Archive_that_was_deferred_as_Too_Recent_do_not_move()
    {
        var now = new DateTimeOffset(2026, 6, 1, 12, 0, 0, TimeSpan.Zero);
        var source = new FakeSource("scans").Add("d/1.jpg", [1], now.AddDays(-1)).Add("d/2.jpg", [2], now.AddSeconds(-1));
        var rule = new ArchiveRuleConfig { Name = "jpgs", Pattern = @"\.jpg$", ArchiveName = "jpgs.zip" };
        var time = new Microsoft.Extensions.Time.Testing.FakeTimeProvider(now);

        await RunAsync(Settings(onSuccess: Done, onFailure: Failed, scan: new ScanConfig { MinFileAgeSeconds = 60 }, rules: [rule]), new FakeRemote(), source, time: time);

        Assert.IsEmpty(source.MovedPaths);
    }
}

/// <summary>Reports a different version of one file from its second Stat on: the first Stat is the Engine's change check after the upload.</summary>
internal sealed class ChangingAfterUploadSource(FakeSource inner, Func<SourceFile?> replacement) : ISource
{
    public string Name => inner.Name;
    public string? RemotePath => inner.RemotePath;
    public IAsyncEnumerable<SourceFile> ListAsync(CancellationToken ct) => inner.ListAsync(ct);
    public async Task<SourceFile?> StatAsync(string relativePath, CancellationToken ct) =>
        relativePath == "a.txt" && replacement() is { } changed ? changed : await inner.StatAsync(relativePath, ct);
    public Task<Stream> OpenReadAsync(string relativePath, CancellationToken ct) => inner.OpenReadAsync(relativePath, ct);
    public Task<MoveResult> MoveAsync(string relativePath, MoveTargetConfig target, CancellationToken ct) => inner.MoveAsync(relativePath, target, ct);
}

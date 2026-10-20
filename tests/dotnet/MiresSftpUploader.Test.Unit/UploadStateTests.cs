using Microsoft.Data.Sqlite;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Time.Testing;
using MiresSftpUploader.Core;
using MiresSftpUploader.Test.Support;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class UploadStateTests
{
    private string _dir = "";

    [TestInitialize]
    public void Setup() => _dir = Directory.CreateTempSubdirectory("mires-state-").FullName;

    [TestCleanup]
    public void Cleanup()
    {
        try { Directory.Delete(_dir, recursive: true); } catch (IOException) { }
    }

    private string DbPath => Path.Combine(_dir, "state.db");

    private EngineSettings Settings(Func<StateSettings, StateSettings>? state = null) => new()
    {
        RemoteRoot = "/upload",
        Destination = "sftp.example:22",
        Retry = new RetrySettings { MaxAttempts = 2, BaseDelay = TimeSpan.Zero, MaxDelay = TimeSpan.Zero },
        State = (state ?? (s => s))(new StateSettings { Path = DbPath }),
    };

    private static Engine NewEngine(EngineSettings settings, TimeProvider time, FakeRemote remote, params ISource[] sources) =>
        new(remote, sources, settings, NullLogger<Engine>.Instance, time);

    private static Task<RunResult> Run(Engine engine, RunOptions? options = null) =>
        engine.RunAsync(options ?? new RunOptions(), new Progress<RunEvent>(), CancellationToken.None);

    [TestMethod]
    public async Task Second_run_skips_unchanged_files_without_reading_them()
    {
        var remote = new FakeRemote();
        var source = new FakeSource("scans").Add("a.txt", "alpha").Add("b.txt", "beta");
        var engine = NewEngine(Settings(), TimeProvider.System, remote, source);
        await Run(engine);
        var readsAfterFirst = source.OpenCount;

        var second = await Run(engine);

        Assert.AreEqual(0, second.ExitCode);
        Assert.AreEqual(2, second.Count(FileOutcome.Skipped));
        Assert.AreEqual(readsAfterFirst, source.OpenCount);
    }

    [TestMethod]
    public async Task Changed_file_is_hashed_and_uploaded_again()
    {
        var remote = new FakeRemote();
        var source = new FakeSource("scans").Add("a.txt", "alpha").Add("b.txt", "beta");
        await Run(NewEngine(Settings(), TimeProvider.System, remote, source));

        source.Add("a.txt", "alpha two"u8.ToArray(), modified: new DateTimeOffset(2026, 2, 1, 0, 0, 0, TimeSpan.Zero));
        var second = await Run(NewEngine(Settings(), TimeProvider.System, remote, source));

        Assert.AreEqual(1, second.Count(FileOutcome.Succeeded));
        Assert.AreEqual(1, second.Count(FileOutcome.Skipped));
        Assert.AreEqual("alpha two", remote.ReadText("/upload/scans/a.txt"));
    }

    [TestMethod]
    public async Task Skipped_files_stay_in_the_manifest_with_their_hash()
    {
        var remote = new FakeRemote();
        var source = new FakeSource("scans").Add("a.txt", "alpha");
        await Run(NewEngine(Settings(), TimeProvider.System, remote, source));
        var first = remote.ReadText("/upload/scans/manifest.json");

        await Run(NewEngine(Settings(), TimeProvider.System, remote, source));

        using var before = System.Text.Json.JsonDocument.Parse(first);
        using var after = System.Text.Json.JsonDocument.Parse(remote.ReadText("/upload/scans/manifest.json"));
        Assert.AreEqual(
            before.RootElement.GetProperty("files")[0].GetProperty("sha256").GetString(),
            after.RootElement.GetProperty("files")[0].GetProperty("sha256").GetString());
    }

    [TestMethod]
    public async Task Failed_file_is_retried_by_the_next_run()
    {
        var remote = new FakeRemote();
        remote.Inject(RemoteOperation.Upload, RemoteResult.Failed("disk full"), times: 2, pathContains: "bad.txt");
        var source = new FakeSource("scans").Add("good.txt", "g").Add("bad.txt", "b");
        var first = await Run(NewEngine(Settings(), TimeProvider.System, remote, source));
        Assert.AreEqual(1, first.ExitCode);
        Assert.AreEqual("Failed", UploadState.ReadFiles(DbPath).Single(f => f.RelativePath == "bad.txt").Status);

        var second = await Run(NewEngine(Settings(), TimeProvider.System, remote, source));

        Assert.AreEqual(0, second.ExitCode);
        Assert.AreEqual(1, second.Count(FileOutcome.Succeeded));
        Assert.AreEqual(1, second.Count(FileOutcome.Skipped));
        Assert.AreEqual("b", remote.ReadText("/upload/scans/bad.txt"));
    }

    [TestMethod]
    public async Task Vanished_source_file_becomes_missing_and_remote_copy_is_kept()
    {
        var remote = new FakeRemote();
        var source = new FakeSource("scans").Add("a.txt", "alpha").Add("b.txt", "beta");
        await Run(NewEngine(Settings(), TimeProvider.System, remote, source));

        source.Remove("b.txt");
        var second = await Run(NewEngine(Settings(), TimeProvider.System, remote, source));

        Assert.AreEqual(0, second.ExitCode);
        Assert.AreEqual("Missing", UploadState.ReadFiles(DbPath).Single(f => f.RelativePath == "b.txt").Status);
        Assert.AreEqual("beta", remote.ReadText("/upload/scans/b.txt"));
    }

    [TestMethod]
    public async Task Rehash_all_uploads_unchanged_files_again()
    {
        var remote = new FakeRemote();
        var source = new FakeSource("scans").Add("a.txt", "alpha");
        var engine = NewEngine(Settings(), TimeProvider.System, remote, source);
        await Run(engine);

        var second = await Run(engine, new RunOptions { RehashAll = true });

        Assert.AreEqual(1, second.Count(FileOutcome.Succeeded));
        Assert.AreEqual(0, second.Count(FileOutcome.Skipped));
        Assert.AreEqual(2, source.OpenCount);
    }

    [TestMethod]
    public async Task Reset_state_forces_a_full_reupload_of_that_source_only()
    {
        var remote = new FakeRemote();
        var scans = new FakeSource("scans").Add("a.txt", "alpha");
        var docs = new FakeSource("docs").Add("d.txt", "delta");
        var engine = NewEngine(Settings(), TimeProvider.System, remote, scans, docs);
        await Run(engine);

        var second = await Run(engine, new RunOptions { ResetSources = ["scans"] });

        Assert.AreEqual(1, second.Count(FileOutcome.Succeeded));
        Assert.AreEqual(1, second.Count(FileOutcome.Skipped));
        Assert.AreEqual(2, scans.OpenCount);
        Assert.AreEqual(1, docs.OpenCount);
        Assert.AreEqual("alpha", remote.ReadText("/upload/scans/a.txt"), "the tool never deletes remote files");
    }

    [TestMethod]
    public async Task A_different_destination_is_a_fresh_start()
    {
        var remote = new FakeRemote();
        var source = new FakeSource("scans").Add("a.txt", "alpha");
        await Run(NewEngine(Settings(), TimeProvider.System, remote, source));
        var other = Settings() with { Destination = "other.example:22" };

        var second = await Run(NewEngine(other, TimeProvider.System, remote, source));

        Assert.AreEqual(1, second.Count(FileOutcome.Succeeded));
    }

    [TestMethod]
    public async Task Overlapping_run_exits_4_and_changes_nothing()
    {
        var remote = new FakeRemote();
        var blocking = new BlockingSource("scans");
        var first = Run(NewEngine(Settings(), TimeProvider.System, remote, blocking));
        await blocking.Listing.Task.WaitAsync(TimeSpan.FromSeconds(10));

        var overlapping = await Run(NewEngine(Settings(), TimeProvider.System, new FakeRemote(), new FakeSource("scans").Add("a.txt", "a")));
        blocking.Release.SetResult();
        var firstResult = await first;

        Assert.AreEqual(4, overlapping.ExitCode);
        StringAssert.Contains(overlapping.Reason, "lock");
        Assert.AreEqual(0, firstResult.ExitCode);
        Assert.HasCount(1, UploadState.ReadRuns(DbPath), "the refused Run is not recorded");
    }

    [TestMethod]
    public async Task Lock_is_free_again_after_a_run_ends()
    {
        var source = new FakeSource("scans").Add("a.txt", "a");
        await Run(NewEngine(Settings(), TimeProvider.System, new FakeRemote(), source));

        var second = await Run(NewEngine(Settings(), TimeProvider.System, new FakeRemote(), source));

        Assert.AreEqual(0, second.ExitCode);
    }

    [TestMethod]
    public async Task Lock_left_by_a_dead_process_does_not_block()
    {
        await File.WriteAllTextAsync(DbPath + ".lock", "pid=999999 user=ghost since=2020-01-01T00:00:00Z");

        var result = await Run(NewEngine(Settings(), TimeProvider.System, new FakeRemote(), new FakeSource("scans").Add("a.txt", "a")));

        Assert.AreEqual(0, result.ExitCode);
    }

    [TestMethod]
    public async Task Database_from_a_newer_app_exits_2_and_is_left_alone()
    {
        await using (var connection = new SqliteConnection($"Data Source={DbPath};Pooling=False"))
        {
            await connection.OpenAsync();
            using var command = connection.CreateCommand();
            command.CommandText = "PRAGMA user_version = 99";
            await command.ExecuteNonQueryAsync();
        }

        var result = await Run(NewEngine(Settings(), TimeProvider.System, new FakeRemote(), new FakeSource("scans").Add("a.txt", "a")));

        Assert.AreEqual(2, result.ExitCode);
        StringAssert.Contains(result.Reason, "newer");
    }

    [TestMethod]
    public async Task Run_that_died_is_abandoned_and_its_recorded_part_file_is_removed()
    {
        var time = new FakeTimeProvider(new DateTimeOffset(2026, 3, 1, 12, 0, 0, TimeSpan.Zero));
        var remote = new FakeRemote();
        var crashing = new CrashingSource("scans", "a.txt");
        await Assert.ThrowsAsync<InvalidOperationException>(() => Run(NewEngine(Settings(), time, remote, crashing)));
        await using (var session = (await remote.ConnectAsync(default)).Value!)
        {
            await session.EnsureDirectoryAsync("/upload/scans", default);
            await session.UploadAsync(new MemoryStream("half"u8.ToArray()), "/upload/scans/a.txt.part", default);
            await session.UploadAsync(new MemoryStream("stray"u8.ToArray()), "/upload/scans/other.bin.part", default);
        }
        Assert.AreEqual("Uploading", UploadState.ReadFiles(DbPath).Single().Status);

        time.Advance(TimeSpan.FromSeconds(61));
        var healthy = new FakeSource("scans").Add("a.txt", "alpha");
        var result = await Run(NewEngine(Settings(), time, remote, healthy));

        Assert.AreEqual(0, result.ExitCode);
        var runs = UploadState.ReadRuns(DbPath);
        Assert.AreEqual("Abandoned", runs[0].Status);
        Assert.AreEqual("Finished", runs[1].Status);
        Assert.IsFalse(remote.Files.ContainsKey("/upload/scans/a.txt.part"));
        Assert.IsTrue(remote.Files.ContainsKey("/upload/scans/other.bin.part"), "only .part files the state recorded are removed");
        Assert.AreEqual("alpha", remote.ReadText("/upload/scans/a.txt"));
    }

    [TestMethod]
    public async Task Run_with_a_fresh_heartbeat_is_not_abandoned()
    {
        var time = new FakeTimeProvider(new DateTimeOffset(2026, 3, 1, 12, 0, 0, TimeSpan.Zero));
        var remote = new FakeRemote();
        await Assert.ThrowsAsync<InvalidOperationException>(() => Run(NewEngine(Settings(), time, remote, new CrashingSource("scans", "a.txt"))));

        time.Advance(TimeSpan.FromSeconds(30));
        await Run(NewEngine(Settings(), time, remote, new FakeSource("scans").Add("a.txt", "a")));

        Assert.AreEqual("Running", UploadState.ReadRuns(DbPath)[0].Status);
    }

    [TestMethod]
    public async Task Missing_files_and_old_run_outcomes_are_pruned_after_their_retention()
    {
        var time = new FakeTimeProvider(new DateTimeOffset(2026, 1, 1, 0, 0, 0, TimeSpan.Zero));
        var remote = new FakeRemote();
        var source = new FakeSource("scans").Add("a.txt", "a").Add("b.txt", "b");
        await Run(NewEngine(Settings(), time, remote, source));
        source.Remove("b.txt");
        time.Advance(TimeSpan.FromDays(1));
        await Run(NewEngine(Settings(), time, remote, source));
        Assert.AreEqual("Missing", UploadState.ReadFiles(DbPath).Single(f => f.RelativePath == "b.txt").Status);

        time.Advance(TimeSpan.FromDays(91));
        await Run(NewEngine(Settings(), time, remote, source));
        CollectionAssert.AreEqual(new[] { "a.txt" }, UploadState.ReadFiles(DbPath).Select(f => f.RelativePath).ToArray());
        Assert.IsTrue(UploadState.ReadRuns(DbPath).All(r => r.FileCount > 0));

        time.Advance(TimeSpan.FromDays(100));
        await Run(NewEngine(Settings(), time, remote, source));
        var runs = UploadState.ReadRuns(DbPath);
        Assert.AreEqual(0, runs[0].FileCount, "first Run is older than 180 days");
        Assert.IsGreaterThan(0, runs[^1].FileCount);
    }

    [TestMethod]
    public async Task Retention_is_configurable()
    {
        var time = new FakeTimeProvider(new DateTimeOffset(2026, 1, 1, 0, 0, 0, TimeSpan.Zero));
        var settings = Settings(s => s with { RunFilesRetention = TimeSpan.FromDays(1) });
        var source = new FakeSource("scans").Add("a.txt", "a");
        await Run(NewEngine(settings, time, new FakeRemote(), source));

        time.Advance(TimeSpan.FromDays(2));
        await Run(NewEngine(settings, time, new FakeRemote(), source));

        Assert.AreEqual(0, UploadState.ReadRuns(DbPath)[0].FileCount);
    }

    [TestMethod]
    public async Task Dry_run_records_nothing()
    {
        var source = new FakeSource("scans").Add("a.txt", "a");

        await Run(NewEngine(Settings(), TimeProvider.System, new FakeRemote(), source), new RunOptions { DryRun = true });

        Assert.IsFalse(File.Exists(DbPath));
    }

    [TestMethod]
    public async Task Without_state_settings_every_run_uploads_everything()
    {
        var source = new FakeSource("scans").Add("a.txt", "a");
        var settings = Settings() with { State = new StateSettings() };
        var engine = NewEngine(settings, TimeProvider.System, new FakeRemote(), source);

        await Run(engine);
        var second = await Run(engine);

        Assert.AreEqual(1, second.Count(FileOutcome.Succeeded));
    }

    [TestMethod]
    public async Task Many_files_are_recorded_through_the_batched_writer()
    {
        var source = new FakeSource("scans");
        for (var i = 0; i < 600; i++) source.Add($"d{i % 10}/f{i}.txt", $"content {i}");
        var remote = new FakeRemote();

        await Run(NewEngine(Settings(), TimeProvider.System, remote, source));
        var second = await Run(NewEngine(Settings(), TimeProvider.System, remote, source));

        Assert.AreEqual(600, UploadState.ReadFiles(DbPath).Count(f => f.Status == "Succeeded"));
        Assert.AreEqual(600, second.Count(FileOutcome.Skipped));
    }

    private sealed class BlockingSource(string name) : ISource
    {
        public TaskCompletionSource Listing { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public TaskCompletionSource Release { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public string Name { get; } = name;
        public string? RemotePath => null;

        public async IAsyncEnumerable<SourceFile> ListAsync([System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken cancellationToken)
        {
            Listing.TrySetResult();
            await Release.Task.WaitAsync(cancellationToken);
            yield break;
        }

        public Task<SourceFile?> StatAsync(string relativePath, CancellationToken cancellationToken) => throw new NotSupportedException();

        public Task<Stream> OpenReadAsync(string relativePath, CancellationToken cancellationToken) => throw new NotSupportedException();
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

        public Task<SourceFile?> StatAsync(string relativePath, CancellationToken cancellationToken) => throw new NotSupportedException();

        public Task<Stream> OpenReadAsync(string relativePath, CancellationToken cancellationToken) =>
            throw new InvalidOperationException("simulated crash");
    }
}

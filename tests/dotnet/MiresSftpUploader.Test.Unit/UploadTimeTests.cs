using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Time.Testing;
using MiresSftpUploader.Core;
using MiresSftpUploader.Test.Support;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class UploadTimeTests
{
    private string _dir = "";

    [TestInitialize]
    public void Setup() => _dir = Directory.CreateTempSubdirectory("mires-uploadtime-").FullName;

    [TestCleanup]
    public void Cleanup()
    {
        try { Directory.Delete(_dir, recursive: true); } catch (IOException) { }
    }

    private string DbPath => Path.Combine(_dir, "data", "state.db");

    private EngineSettings Settings(int attempts = 1, ArchiveConfig? archive = null) => new()
    {
        RemoteRoot = "/upload",
        Destination = "sftp.example:22",
        Retry = new RetrySettings { MaxAttempts = attempts, BaseDelay = TimeSpan.Zero, MaxDelay = TimeSpan.Zero },
        State = new StateSettings { AccessGroup = TestAccessGroup.Name, Path = DbPath },
        Archive = (archive ?? new ArchiveConfig()) with { StagingPath = Path.Combine(_dir, "staging") },
    };

    private static readonly DateTimeOffset Start = new(2026, 3, 1, 12, 0, 0, TimeSpan.Zero);

    /// <summary>A remote whose uploads of paths containing <paramref name="pathContains"/> take the given durations, one per call.</summary>
    private static FakeRemote SlowUploads(FakeTimeProvider time, string pathContains, params int[] seconds)
    {
        var remote = new FakeRemote();
        var calls = 0;
        remote.OnUpload = (path, _) =>
        {
            if (path.Contains(pathContains, StringComparison.Ordinal)) time.Advance(TimeSpan.FromSeconds(seconds[Math.Min(calls++, seconds.Length - 1)]));
            return Task.CompletedTask;
        };
        return remote;
    }

    private async Task<(RunResult Result, List<RunEvent> Events)> RunAsync(FakeRemote remote, ISource source, FakeTimeProvider time, EngineSettings settings)
    {
        var events = new List<RunEvent>();
        var result = await new Engine(remote, [source], settings, NullLogger<Engine>.Instance, time)
            .RunAsync(new RunOptions(), new SyncProgress(events), CancellationToken.None);
        return (result, events);
    }

    private sealed class SyncProgress(List<RunEvent> events) : IProgress<RunEvent>
    {
        public void Report(RunEvent value) { lock (events) events.Add(value); }
    }

    private RunFileOutcome FileOf(RunResult result, string path) =>
        new RunHistory(Settings().State, TimeProvider.System).GetRun(result.RunId)!.Files.Single(f => f.RelativePath == path);

    [TestMethod]
    public async Task A_succeeded_file_stores_the_Upload_Time_of_its_upload_call()
    {
        var time = new FakeTimeProvider(Start);
        var (result, _) = await RunAsync(SlowUploads(time, "a.txt", 3), new FakeSource("scans").Add("a.txt", "alpha"), time, Settings());

        var file = FileOf(result, "a.txt");
        Assert.AreEqual("Succeeded", file.Outcome);
        Assert.AreEqual(5, file.Bytes);
        Assert.AreEqual(3000L, file.UploadMs);
    }

    [TestMethod]
    public async Task Upload_Time_covers_only_the_delivering_attempt_not_earlier_attempts_or_backoff()
    {
        var time = new FakeTimeProvider(Start);
        var remote = SlowUploads(time, "a.txt", 10, 3);
        remote.Inject(RemoteOperation.Upload, RemoteResult.Failed("connection reset"), times: 1, pathContains: "a.txt");

        var (result, _) = await RunAsync(remote, new FakeSource("scans").Add("a.txt", "alpha"), time, Settings(attempts: 2));

        var file = FileOf(result, "a.txt");
        Assert.AreEqual("Succeeded", file.Outcome);
        Assert.AreEqual(3000L, file.UploadMs, "only the second, delivering attempt counts");
        Assert.AreEqual(13000L, file.DurationMs, "the whole-file elapsed time keeps its meaning");
    }

    [TestMethod]
    public async Task An_uploaded_Archive_stores_the_Upload_Time_of_the_zip()
    {
        var time = new FakeTimeProvider(Start);
        var archive = new ArchiveConfig
        {
            Rules = [new ArchiveRuleConfig { Name = "tiles", Pattern = @"\.jpg$", Grouping = ArchiveGrouping.PerDirectory, ArchiveName = "{rule}-{dir}.zip", MinFiles = 1 }],
        };
        var (result, _) = await RunAsync(SlowUploads(time, ".zip", 4), new FakeSource("scans").Add("slide/t1.jpg", "t1").Add("slide/t2.jpg", "t2"), time, Settings(archive: archive));

        var zip = FileOf(result, "slide/tiles-slide.zip");
        Assert.AreEqual("Succeeded", zip.Outcome);
        Assert.AreEqual(4000L, zip.UploadMs);
    }

    [TestMethod]
    public async Task The_Succeeded_event_carries_the_bytes_sent_and_the_Upload_Time()
    {
        var time = new FakeTimeProvider(Start);
        var (_, events) = await RunAsync(SlowUploads(time, "a.txt", 3), new FakeSource("scans").Add("a.txt", "alpha"), time, Settings());

        var succeeded = events.OfType<FileOutcomeChanged>().Single(e => e.Outcome == FileOutcome.Succeeded);
        Assert.AreEqual(5L, succeeded.BytesSent);
        Assert.AreEqual(TimeSpan.FromSeconds(3), succeeded.UploadTime);
        Assert.IsTrue(events.OfType<FileOutcomeChanged>().Where(e => e.Outcome != FileOutcome.Succeeded).All(e => e.UploadTime is null && e.BytesSent is null));
    }

    [TestMethod]
    public async Task Reports_carry_Upload_Time_as_the_last_json_field_and_the_last_csv_column()
    {
        var time = new FakeTimeProvider(Start);
        var source = new FakeSource("scans").Add("a.txt", "alpha");
        var json = Path.Combine(_dir, "r.json");
        var csv = Path.Combine(_dir, "r.csv");
        await new Engine(SlowUploads(time, "a.txt", 3), [source], Settings(), NullLogger<Engine>.Instance, time)
            .RunAsync(new RunOptions { ReportPath = json }, new Progress<RunEvent>(), CancellationToken.None);
        await new Engine(SlowUploads(time, "a.txt", 3), [source], Settings(), NullLogger<Engine>.Instance, time)
            .RunAsync(new RunOptions { ReportPath = csv, ReportFormat = ReportFormat.Csv }, new Progress<RunEvent>(), CancellationToken.None);

        using var document = System.Text.Json.JsonDocument.Parse(await File.ReadAllTextAsync(json));
        var first = document.RootElement.GetProperty("files")[0];
        CollectionAssert.AreEqual(new[] { "source", "path", "outcome", "bytes", "durationMs", "reason", "uploadMs" },
            first.EnumerateObject().Select(p => p.Name).ToArray());
        Assert.AreEqual(3000L, first.GetProperty("uploadMs").GetInt64());
        var lines = (await File.ReadAllTextAsync(csv)).Split("\r\n", StringSplitOptions.RemoveEmptyEntries);
        StringAssert.EndsWith(lines[0], ",Bytes,DurationMs,Reason,UploadMs");
        // The second Run found the file unchanged: Skipped, so its Upload Time is empty.
        Assert.AreEqual("Skipped", lines[1].Split(',')[7]);
        StringAssert.EndsWith(lines[1], ",");
    }

    [TestMethod]
    public async Task Migrating_from_schema_3_keeps_the_rows_with_empty_Upload_Time_and_makes_a_backup()
    {
        var time = new FakeTimeProvider(Start);
        var source = new FakeSource("scans").Add("a.txt", "alpha");
        var first = await RunAsync(SlowUploads(time, "a.txt", 3), source, time, Settings());
        // Turn the database back into a schema 3 one.
        using (var connection = UploadStateStore.OpenConnection(DbPath))
        {
            UploadStateStore.Exec(connection, "ALTER TABLE RunFiles DROP COLUMN UploadMs");
            UploadStateStore.Exec(connection, "PRAGMA user_version = 3");
        }

        var second = await RunAsync(new FakeRemote(), source, time, Settings());

        Assert.AreEqual(0, second.Result.ExitCode);
        Assert.HasCount(1, Directory.GetFiles(Path.GetDirectoryName(DbPath)!, "state.db.v3-*.bak"));
        var old = FileOf(first.Result, "a.txt");
        Assert.AreEqual("Succeeded", old.Outcome);
        Assert.AreEqual(5, old.Bytes);
        Assert.IsNull(old.UploadMs, "no backfill");
    }

    [TestMethod]
    public async Task The_History_reads_a_schema_3_database_before_any_Run_has_migrated_it()
    {
        var time = new FakeTimeProvider(Start);
        var first = await RunAsync(SlowUploads(time, "a.txt", 3), new FakeSource("scans").Add("a.txt", "alpha"), time, Settings());
        using (var connection = UploadStateStore.OpenConnection(DbPath))
        {
            UploadStateStore.Exec(connection, "ALTER TABLE RunFiles DROP COLUMN UploadMs");
            UploadStateStore.Exec(connection, "PRAGMA user_version = 3");
        }

        var file = FileOf(first.Result, "a.txt");

        Assert.AreEqual("Succeeded", file.Outcome);
        Assert.IsNull(file.UploadMs);
    }

    [TestMethod]
    public async Task Failed_and_skipped_rows_leave_Upload_Time_empty()
    {
        var time = new FakeTimeProvider(Start);
        var remote = SlowUploads(time, "", 2);
        var source = new FakeSource("scans").Add("a.txt", "alpha");
        await RunAsync(remote, source, time, Settings());
        source.Add("b.txt", "beta");
        remote.Inject(RemoteOperation.Upload, RemoteResult.Failed("disk full"), times: 5, pathContains: "b.txt");

        var (second, _) = await RunAsync(remote, source, time, Settings());

        Assert.AreEqual("Skipped", FileOf(second, "a.txt").Outcome);
        Assert.IsNull(FileOf(second, "a.txt").UploadMs);
        Assert.AreEqual("Failed", FileOf(second, "b.txt").Outcome);
        Assert.IsNull(FileOf(second, "b.txt").UploadMs);
    }
}

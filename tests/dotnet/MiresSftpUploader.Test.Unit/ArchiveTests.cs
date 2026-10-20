using System.IO.Compression;
using System.Security.Cryptography;
using System.Text.Json;
using Microsoft.Extensions.Logging.Abstractions;
using MiresSftpUploader.Core;
using MiresSftpUploader.Test.Support;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class ArchiveTests
{
    private string _dir = "";

    [TestInitialize]
    public void Setup() => _dir = Directory.CreateTempSubdirectory("mires-archive-").FullName;

    [TestCleanup]
    public void Cleanup()
    {
        try { Directory.Delete(_dir, recursive: true); } catch (IOException) { }
    }

    private string DbPath => Path.Combine(_dir, "data", "state.db");
    private string StagingRoot => Path.Combine(_dir, "data", "staging");

    private static ArchiveRuleConfig Rule(string name, string pattern, ArchiveGrouping grouping = ArchiveGrouping.PerDirectory,
        string archiveName = "{rule}-{dir}.zip", int minFiles = 1) =>
        new() { Name = name, Pattern = pattern, Grouping = grouping, ArchiveName = archiveName, MinFiles = minFiles };

    private EngineSettings Settings(ArchiveConfig? archive = null, bool withState = false, ScanConfig? scan = null, long minFree = 0) => new()
    {
        RemoteRoot = "/upload",
        Destination = "sftp.example:22",
        Retry = new RetrySettings { MaxAttempts = 1, BaseDelay = TimeSpan.Zero, MaxDelay = TimeSpan.Zero },
        State = withState ? new StateSettings { Path = DbPath } : new StateSettings(),
        Archive = (archive ?? new ArchiveConfig()) with { StagingPath = StagingRoot, MinFreeSpaceBytes = minFree },
        Scan = scan ?? new ScanConfig(),
    };

    private static ArchiveConfig Rules(params ArchiveRuleConfig[] rules) => new() { Rules = rules };

    private static Task<RunResult> RunAsync(EngineSettings settings, FakeRemote remote, RunOptions? options = null,
        IProgress<RunEvent>? progress = null, TimeProvider? time = null, params ISource[] sources) =>
        new Engine(remote, sources, settings, NullLogger<Engine>.Instance, time ?? TimeProvider.System)
            .RunAsync(options ?? new RunOptions(), progress ?? new Progress<RunEvent>(), CancellationToken.None);

    private static string Sha256(byte[] data) => Convert.ToHexStringLower(SHA256.HashData(data));

    private static Dictionary<string, byte[]> ZipEntries(byte[] zip)
    {
        using var archive = new ZipArchive(new MemoryStream(zip), ZipArchiveMode.Read);
        return archive.Entries.ToDictionary(e => e.FullName, e =>
        {
            using var s = e.Open();
            using var m = new MemoryStream();
            s.CopyTo(m);
            return m.ToArray();
        });
    }

    [TestMethod]
    public async Task Per_directory_rule_uploads_one_archive_per_directory_instead_of_its_matching_files()
    {
        var remote = new FakeRemote();
        var source = new FakeSource("scans")
            .Add("slide/tile1.jpg", "t1").Add("slide/tile2.jpg", "t2").Add("slide/meta.txt", "meta")
            .Add("slide/deep/tile3.jpg", "t3");

        var result = await RunAsync(Settings(Rules(Rule("tiles", @"\.jpg$"))), remote, sources: source);

        Assert.AreEqual(0, result.ExitCode);
        Assert.AreEqual(4, result.Count(FileOutcome.Succeeded));
        Assert.IsFalse(remote.Files.ContainsKey("/upload/scans/slide/tile1.jpg"), "members are uploaded inside the Archive only");
        Assert.AreEqual("meta", remote.ReadText("/upload/scans/slide/meta.txt"));
        var top = ZipEntries(remote.Files["/upload/scans/slide/tiles-slide.zip"]);
        CollectionAssert.AreEquivalent(new[] { "tile1.jpg", "tile2.jpg" }, top.Keys.ToArray());
        Assert.AreEqual("t1", System.Text.Encoding.UTF8.GetString(top["tile1.jpg"]));
        var nested = ZipEntries(remote.Files["/upload/scans/slide/deep/tiles-deep.zip"]);
        CollectionAssert.AreEquivalent(new[] { "tile3.jpg" }, nested.Keys.ToArray());
        Assert.IsFalse(remote.Files.Keys.Any(k => k.EndsWith(".part")));
    }

    private sealed class Events : IProgress<RunEvent>
    {
        public List<RunEvent> All { get; } = [];
        public void Report(RunEvent value) { lock (All) All.Add(value); }
        public FileOutcomeChanged Last(string path) => All.OfType<FileOutcomeChanged>().Last(e => e.RelativePath == path);
        public IReadOnlyList<ArchivePlanned> Planned => All.OfType<ArchivePlanned>().ToList();
    }

    private static JsonDocument Manifest(FakeRemote remote, string path = "/upload/scans/manifest.json") =>
        JsonDocument.Parse(remote.ReadText(path));

    private static byte[] Bytes(string text) => System.Text.Encoding.UTF8.GetBytes(text);

    [TestMethod]
    public async Task Per_rule_archive_goes_in_the_source_root_and_a_group_below_MinFiles_stays_individual()
    {
        var remote = new FakeRemote();
        var source = new FakeSource("scans")
            .Add("a/one.dcm", "1").Add("b/two.dcm", "2").Add("b/deep/three.dcm", "3")
            .Add("x/notes.txt", "n1").Add("y/notes.txt", "n2");
        var time = new Microsoft.Extensions.Time.Testing.FakeTimeProvider(new DateTimeOffset(2026, 6, 1, 12, 0, 0, TimeSpan.Zero));
        var archive = Rules(
            Rule("dicom", @"\.dcm$", ArchiveGrouping.PerRule, "{rule}-{date}.zip"),
            Rule("text", @"\.txt$", ArchiveGrouping.PerRule, "{rule}.zip", minFiles: 3));

        var result = await RunAsync(Settings(archive), remote, time: time, sources: source);

        Assert.AreEqual(0, result.ExitCode);
        var entries = ZipEntries(remote.Files["/upload/scans/dicom-20260601.zip"]);
        CollectionAssert.AreEquivalent(new[] { "a/one.dcm", "b/two.dcm", "b/deep/three.dcm" }, entries.Keys.ToArray());
        Assert.AreEqual("n1", remote.ReadText("/upload/scans/x/notes.txt"));
        Assert.AreEqual("n2", remote.ReadText("/upload/scans/y/notes.txt"));
        Assert.IsFalse(remote.Files.ContainsKey("/upload/scans/text.zip"));
    }

    [TestMethod]
    public async Task First_matching_rule_wins_and_Ignore_beats_Archive()
    {
        var remote = new FakeRemote();
        var source = new FakeSource("scans")
            .Add("a/x.jpg", "x").Add("a/y.png", "y").Add("a/.DS_Store", "junk");
        var archive = Rules(Rule("first", @"\.jpg$"), Rule("second", @"^a/"), Rule("third", ".*"));

        var result = await RunAsync(Settings(archive), remote, sources: source);

        Assert.AreEqual(1, result.Count(FileOutcome.Ignored));
        CollectionAssert.AreEquivalent(new[] { "x.jpg" }, ZipEntries(remote.Files["/upload/scans/a/first-a.zip"]).Keys.ToArray());
        CollectionAssert.AreEquivalent(new[] { "y.png" }, ZipEntries(remote.Files["/upload/scans/a/second-a.zip"]).Keys.ToArray());
        Assert.IsFalse(remote.Files.Keys.Any(k => k.Contains("third")), "an Ignored file never reaches a later rule");
        Assert.IsFalse(remote.Files.Keys.Any(k => k.Contains("DS_Store")));
    }

    [TestMethod]
    public async Task Manifest_lists_each_archive_with_its_members_hashes_and_modified_times()
    {
        var remote = new FakeRemote();
        var modified = new DateTimeOffset(2025, 3, 4, 5, 6, 7, TimeSpan.Zero);
        var source = new FakeSource("scans").Add("d/a.jpg", Bytes("alpha"), modified).Add("d/b.jpg", Bytes("beta"), modified).Add("d/c.txt", "gamma");

        await RunAsync(Settings(Rules(Rule("tiles", @"\.jpg$"))), remote, sources: source);

        using var manifest = Manifest(remote);
        var zipBytes = remote.Files["/upload/scans/d/tiles-d.zip"];
        var archive = manifest.RootElement.GetProperty("archives").EnumerateArray().Single();
        Assert.AreEqual("d/tiles-d.zip", archive.GetProperty("path").GetString());
        Assert.AreEqual(Sha256(zipBytes), archive.GetProperty("sha256").GetString(), "Manifest hash equals the hash of the uploaded Archive");
        var members = archive.GetProperty("members").EnumerateArray().ToDictionary(m => m.GetProperty("path").GetString()!);
        Assert.AreEqual(Sha256(Bytes("alpha")), members["d/a.jpg"].GetProperty("sha256").GetString());
        Assert.AreEqual("a.jpg", members["d/a.jpg"].GetProperty("entry").GetString());
        Assert.AreEqual(modified, members["d/b.jpg"].GetProperty("modified").GetDateTimeOffset());
        var plainFiles = manifest.RootElement.GetProperty("files").EnumerateArray().Select(f => f.GetProperty("path").GetString()).ToArray();
        CollectionAssert.AreEqual(new[] { "d/c.txt" }, plainFiles, "members are not listed as plain files");
    }

    [TestMethod]
    public async Task Identical_members_give_byte_identical_archives_whatever_their_modification_times()
    {
        async Task<byte[]> Build(DateTimeOffset modified, string order)
        {
            var remote = new FakeRemote();
            var source = new FakeSource("scans");
            foreach (var name in order.Split(','))
                source.Add($"d/{name}.bin", Bytes("content of " + name), modified);
            await RunAsync(Settings(Rules(Rule("tiles", @"\.bin$"))), remote, sources: source);
            return remote.Files["/upload/scans/d/tiles-d.zip"];
        }

        var first = await Build(new DateTimeOffset(2020, 1, 1, 0, 0, 0, TimeSpan.Zero), "b,a,c");
        var second = await Build(new DateTimeOffset(2026, 9, 9, 9, 9, 9, TimeSpan.Zero), "c,b,a");

        CollectionAssert.AreEqual(first, second);
    }

    [TestMethod]
    public async Task Archive_bytes_match_the_golden_file()
    {
        // Release checklist item 7: this file must be byte-identical on every OS. Regenerate deliberately with MIRES_UPDATE_GOLDEN=1.
        var remote = new FakeRemote();
        var source = new FakeSource("scans")
            .Add("slide/ångström.jpg", new byte[] { 0, 1, 2, 3, 4, 5, 6, 7, 8, 9 })
            .Add("slide/sub/empty.jpg", Array.Empty<byte>())
            .Add("slide/tile-0001.jpg", Bytes("The quick brown fox jumps over the lazy dog\n"));

        await RunAsync(Settings(Rules(Rule("tiles", @"\.jpg$", ArchiveGrouping.PerRule, "golden.zip"))), remote, sources: source);

        var actual = remote.Files["/upload/scans/golden.zip"];
        if (Environment.GetEnvironmentVariable("MIRES_UPDATE_GOLDEN") == "1")
            File.WriteAllBytes(Path.Combine(FindTestProjectDirectory(), "Golden", "archive.zip"), actual);
        else
            CollectionAssert.AreEqual(File.ReadAllBytes(Path.Combine(AppContext.BaseDirectory, "Golden", "archive.zip")), actual,
                "the Archive differs from the golden file");

        using var zip = new ZipArchive(new MemoryStream(actual), ZipArchiveMode.Read);
        Assert.IsTrue(zip.Entries.All(e => e.Length == e.CompressedLength), "entries are stored, not compressed");
        Assert.IsTrue(zip.Entries.All(e => e.LastWriteTime.DateTime == new DateTime(1980, 1, 1)), "fixed timestamp");
        CollectionAssert.AreEqual(
            new[] { "slide/sub/empty.jpg", "slide/tile-0001.jpg", "slide/ångström.jpg" },
            zip.Entries.Select(e => e.FullName).ToArray(), "entries are sorted ordinally and UTF-8 encoded");
    }

    private static string FindTestProjectDirectory()
    {
        var directory = new DirectoryInfo(AppContext.BaseDirectory);
        while (directory is not null && !File.Exists(Path.Combine(directory.FullName, "MiresSftpUploader.Test.Unit.csproj")))
            directory = directory.Parent;
        return directory?.FullName ?? throw new InvalidOperationException("test project directory not found");
    }

    [TestMethod]
    public async Task Unchanged_archive_is_skipped_without_reading_members_and_any_member_change_rebuilds_the_whole_archive()
    {
        var remote = new FakeRemote();
        var source = new FakeSource("scans").Add("d/a.jpg", "alpha").Add("d/b.jpg", "beta");
        var settings = Settings(Rules(Rule("tiles", @"\.jpg$")), withState: true);

        await RunAsync(settings, remote, sources: source);
        var firstZip = remote.Files["/upload/scans/d/tiles-d.zip"];
        var opensAfterFirst = source.OpenCount;

        var second = await RunAsync(settings, remote, sources: source);
        Assert.AreEqual(2, second.Count(FileOutcome.Skipped));
        Assert.AreEqual(opensAfterFirst, source.OpenCount, "the fast path reads no member");

        source.Add("d/b.jpg", "beta changed", new DateTimeOffset(2026, 2, 2, 0, 0, 0, TimeSpan.Zero));
        var third = await RunAsync(settings, remote, sources: source);
        Assert.AreEqual(2, third.Count(FileOutcome.Succeeded), "both members count: the whole Archive is rebuilt and uploaded");
        Assert.AreNotEqual(Sha256(firstZip), Sha256(remote.Files["/upload/scans/d/tiles-d.zip"]));
        Assert.AreEqual("beta changed", System.Text.Encoding.UTF8.GetString(ZipEntries(remote.Files["/upload/scans/d/tiles-d.zip"])["b.jpg"]));
    }

    [TestMethod]
    public async Task A_touched_member_with_the_same_content_skips_the_upload_and_restores_the_fast_path()
    {
        var remote = new FakeRemote();
        var source = new FakeSource("scans").Add("d/a.jpg", "alpha").Add("d/b.jpg", "beta");
        var settings = Settings(Rules(Rule("tiles", @"\.jpg$")), withState: true);
        await RunAsync(settings, remote, sources: source);

        source.Add("d/a.jpg", "alpha", new DateTimeOffset(2026, 5, 5, 0, 0, 0, TimeSpan.Zero));
        remote.Inject(RemoteOperation.Upload, RemoteResult.Failed("must not upload"), times: 100);
        var second = await RunAsync(settings, remote, sources: source);
        var opens = source.OpenCount;
        var third = await RunAsync(settings, remote, sources: source);

        Assert.AreEqual(2, second.Count(FileOutcome.Skipped), "same paths and hashes: nothing to upload");
        Assert.AreEqual(0, second.ExitCode);
        Assert.AreEqual(2, third.Count(FileOutcome.Skipped));
        Assert.AreEqual(opens, source.OpenCount, "the refreshed state allows the fast path again");
    }

    [TestMethod]
    public async Task A_member_that_changes_while_it_is_read_fails_the_whole_archive_and_names_the_culprit()
    {
        var remote = new FakeRemote();
        var source = new FakeSource("scans").Add("d/a.jpg", "alpha").Add("d/b.jpg", "beta").Add("e/c.jpg", "gamma");
        source.AfterOpen = path =>
        {
            if (path == "d/b.jpg") source.Add("d/b.jpg", "beta, still being written", new DateTimeOffset(2026, 7, 7, 0, 0, 0, TimeSpan.Zero));
        };
        var events = new Events();

        var result = await RunAsync(Settings(Rules(Rule("tiles", @"\.jpg$"))), remote, progress: events, sources: source);

        Assert.AreEqual(1, result.ExitCode);
        Assert.AreEqual(2, result.Count(FileOutcome.Failed));
        foreach (var path in new[] { "d/a.jpg", "d/b.jpg" })
        {
            StringAssert.Contains(events.Last(path).Reason, "ChangedDuringArchive");
            StringAssert.Contains(events.Last(path).Reason, "d/b.jpg");
        }
        Assert.IsFalse(remote.Files.Keys.Any(k => k.Contains("tiles-d")), "all or nothing");
        Assert.IsTrue(remote.Files.ContainsKey("/upload/scans/e/tiles-e.zip"), "other Archives continue");
    }

    [TestMethod]
    public async Task Retrying_a_run_rebuilds_its_failed_archives_and_keeps_delivered_ones_in_the_manifest()
    {
        var remote = new FakeRemote();
        var source = new FakeSource("scans").Add("d/a.jpg", "alpha").Add("d/b.jpg", "beta").Add("e/c.jpg", "gamma");
        source.AfterOpen = path =>
        {
            if (path == "d/b.jpg") source.Add("d/b.jpg", "beta, finished", new DateTimeOffset(2026, 7, 7, 0, 0, 0, TimeSpan.Zero));
        };
        var settings = Settings(Rules(Rule("tiles", @"\.jpg$")), withState: true);
        var first = await RunAsync(settings, remote, sources: source);
        Assert.AreEqual(1, first.ExitCode);
        source.AfterOpen = null;

        var retry = await RunAsync(settings, remote, new RunOptions { RetryOf = first.RunId }, sources: source);

        Assert.AreEqual(0, retry.ExitCode);
        Assert.AreEqual(2, retry.Count(FileOutcome.Succeeded));
        Assert.AreEqual("beta, finished", System.Text.Encoding.UTF8.GetString(ZipEntries(remote.Files["/upload/scans/d/tiles-d.zip"])["b.jpg"]));
        using var manifest = Manifest(remote);
        Assert.IsTrue(manifest.RootElement.GetProperty("complete").GetBoolean());
        var archives = manifest.RootElement.GetProperty("archives").EnumerateArray().ToDictionary(a => a.GetProperty("path").GetString()!);
        CollectionAssert.AreEquivalent(new[] { "d/tiles-d.zip", "e/tiles-e.zip" }, archives.Keys.ToArray());
        Assert.AreEqual(1, archives["e/tiles-e.zip"].GetProperty("members").GetArrayLength(), "the archive delivered earlier keeps its members");
        Assert.AreEqual(Sha256(Bytes("gamma")), archives["e/tiles-e.zip"].GetProperty("members")[0].GetProperty("sha256").GetString());
    }

    [TestMethod]
    public async Task A_member_that_changes_between_scan_and_build_fails_the_archive()
    {
        var remote = new FakeRemote();
        var source = new FakeSource("scans").Add("d/a.jpg", "alpha");
        source.AfterListing = () => source.Add("d/a.jpg", "alpha!", new DateTimeOffset(2026, 7, 7, 0, 0, 0, TimeSpan.Zero));
        var events = new Events();

        var result = await RunAsync(Settings(Rules(Rule("tiles", @"\.jpg$"))), remote, progress: events, sources: source);

        Assert.AreEqual(1, result.ExitCode);
        StringAssert.Contains(events.Last("d/a.jpg").Reason, "ChangedDuringArchive");
        Assert.IsFalse(remote.Files.Keys.Any(k => k.EndsWith(".zip")));
    }

    [TestMethod]
    public async Task Too_little_staging_space_fails_that_archive_with_InsufficientStagingSpace_and_the_run_continues()
    {
        var remote = new FakeRemote();
        var source = new FakeSource("scans").Add("d/a.jpg", "alpha").Add("plain.txt", "p");
        var events = new Events();

        var result = await RunAsync(Settings(Rules(Rule("tiles", @"\.jpg$")), minFree: long.MaxValue), remote, progress: events, sources: source);

        Assert.AreEqual(1, result.ExitCode);
        StringAssert.Contains(events.Last("d/a.jpg").Reason, "InsufficientStagingSpace");
        Assert.AreEqual("p", remote.ReadText("/upload/scans/plain.txt"));
    }

    [TestMethod]
    public async Task Staging_area_is_removed_at_the_end_of_the_run_and_leftovers_of_dead_runs_are_swept()
    {
        var leftover = Path.Combine(StagingRoot, Guid.NewGuid().ToString());
        Directory.CreateDirectory(leftover);
        File.WriteAllText(Path.Combine(leftover, "dead.zip"), "x");
        var source = new FakeSource("scans").Add("d/a.jpg", "alpha");

        await RunAsync(Settings(Rules(Rule("tiles", @"\.jpg$")), withState: true), new FakeRemote(), sources: source);

        Assert.IsEmpty(Directory.Exists(StagingRoot) ? Directory.GetFileSystemEntries(StagingRoot) : [], "no Staging Area survives the Run");
    }

    [TestMethod]
    public async Task Archive_name_equal_to_an_ordinary_file_is_a_collision_found_at_planning()
    {
        var remote = new FakeRemote();
        var source = new FakeSource("scans").Add("d/a.jpg", "alpha").Add("d/tiles-d.zip", "I am a real file");
        var events = new Events();

        var result = await RunAsync(Settings(Rules(Rule("tiles", @"\.jpg$"))), remote, progress: events, sources: source);

        Assert.AreEqual(1, result.ExitCode);
        StringAssert.Contains(events.Last("d/a.jpg").Reason, "ArchiveNameCollision");
        Assert.AreEqual("I am a real file", remote.ReadText("/upload/scans/d/tiles-d.zip"), "the ordinary file is untouched");
    }

    [TestMethod]
    public async Task Dry_run_lists_each_archive_and_builds_and_records_nothing()
    {
        var source = new FakeSource("scans")
            .Add("d/a.jpg", "alpha").Add("d/b.jpg", "beta").Add("c/x.jpg", "x").Add("c/tiles-c.zip", "taken");
        var events = new Events();
        var remote = new FakeRemote();

        var result = await RunAsync(Settings(Rules(Rule("tiles", @"\.jpg$")), withState: true), remote,
            new RunOptions { DryRun = true }, events, sources: source);

        Assert.AreEqual(0, result.ExitCode);
        var planned = events.Planned.ToDictionary(p => p.Name);
        Assert.AreEqual(new ArchivePlanned("scans", "d/tiles-d.zip", "tiles", 2, 9, 9, "WouldBuild"), planned["d/tiles-d.zip"]);
        Assert.AreEqual("ArchiveNameCollision", planned["c/tiles-c.zip"].Status);
        Assert.AreEqual(0, remote.ConnectCount);
        Assert.AreEqual(0, source.OpenCount, "a Dry Run reads no member");
        Assert.IsFalse(Directory.Exists(Path.Combine(_dir, "data")), "no staging folder, database or lock");
    }

    [TestMethod]
    public async Task Dry_run_reports_skip_status_from_the_upload_state()
    {
        var source = new FakeSource("scans").Add("d/a.jpg", "alpha").Add("d/b.jpg", "beta");
        var settings = Settings(Rules(Rule("tiles", @"\.jpg$")), withState: true);
        await RunAsync(settings, new FakeRemote(), sources: source);

        async Task<string> DryStatus()
        {
            var events = new Events();
            await RunAsync(settings, new FakeRemote(), new RunOptions { DryRun = true }, events, sources: source);
            return events.Planned.Single().Status;
        }

        Assert.AreEqual("WouldSkip", await DryStatus());
        source.Add("d/a.jpg", "alpha", new DateTimeOffset(2026, 5, 5, 0, 0, 0, TimeSpan.Zero));
        Assert.AreEqual("NeedsHashing", await DryStatus());
        source.Add("d/c.jpg", "new member");
        Assert.AreEqual("WouldBuild", await DryStatus());
    }

    [TestMethod]
    public async Task An_archive_with_a_too_recent_member_is_deferred_whole_until_the_member_ages()
    {
        var now = new DateTimeOffset(2026, 6, 1, 12, 0, 0, TimeSpan.Zero);
        var time = new Microsoft.Extensions.Time.Testing.FakeTimeProvider(now);
        var remote = new FakeRemote();
        var source = new FakeSource("scans").Add("d/old.jpg", Bytes("old"), now.AddDays(-1)).Add("d/fresh.jpg", Bytes("fresh"), now.AddSeconds(-1));
        var settings = Settings(Rules(Rule("tiles", @"\.jpg$")), scan: new ScanConfig { MinFileAgeSeconds = 60 });
        var events = new Events();

        var first = await RunAsync(settings, remote, progress: events, time: time, sources: source);

        Assert.AreEqual(0, first.ExitCode);
        Assert.AreEqual(2, first.Count(FileOutcome.Skipped));
        Assert.AreEqual("TooRecent", events.Last("d/old.jpg").Reason);
        Assert.IsFalse(remote.Files.Keys.Any(k => k.EndsWith(".zip")));

        time.Advance(TimeSpan.FromMinutes(5));
        var second = await RunAsync(settings, remote, time: time, sources: source);
        Assert.AreEqual(2, second.Count(FileOutcome.Succeeded));
        Assert.IsTrue(remote.Files.ContainsKey("/upload/scans/d/tiles-d.zip"));
    }
}

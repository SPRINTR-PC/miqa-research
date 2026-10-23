using System.Text.Json;
using Microsoft.Extensions.Logging.Abstractions;
using MiresSftpUploader.Core;
using MiresSftpUploader.Test.Support;

namespace MiresSftpUploader.Test.Unit;

/// <summary>PartThenRename versus Direct, and the RemoteDenied failure of a server that refuses to replace an object.</summary>
[TestClass]
public sealed class UploadStrategyTests
{
    private string _dir = "";

    [TestInitialize]
    public void Setup() => _dir = Directory.CreateTempSubdirectory("mires-strategy-").FullName;

    [TestCleanup]
    public void Cleanup()
    {
        try { Directory.Delete(_dir, recursive: true); } catch (IOException) { }
    }

    private EngineSettings Settings(UploadStrategy strategy, RemoteAccess access = RemoteAccess.WriteOnly, VerificationSettings? verification = null,
        ArchiveConfig? archive = null) => new()
    {
        RemoteRoot = "/upload",
        Destination = "sftp.example:22",
        RemoteAccess = access,
        UploadStrategy = strategy,
        Verification = verification ?? new VerificationSettings(),
        Retry = new RetrySettings { MaxAttempts = 2, BaseDelay = TimeSpan.Zero, MaxDelay = TimeSpan.Zero },
        State = new StateSettings { AccessGroup = TestAccessGroup.Name, Path = Path.Combine(_dir, "state.db") },
        Archive = (archive ?? new ArchiveConfig()) with { StagingPath = Path.Combine(_dir, "staging"), MinFreeSpaceBytes = 0 },
    };

    private sealed class Outcomes : IProgress<RunEvent>
    {
        private readonly Dictionary<string, FileOutcomeChanged> _last = new();
        public void Report(RunEvent value)
        {
            if (value is FileOutcomeChanged changed) lock (_last) _last[changed.RelativePath] = changed;
        }
        public FileOutcomeChanged Of(string path) { lock (_last) return _last[path]; }
    }

    private static async Task<(RunResult Result, Outcomes Files)> RunWithOutcomes(EngineSettings settings, FakeRemote remote, FakeSource source)
    {
        var outcomes = new Outcomes();
        var result = await new Engine(remote, [source], settings, NullLogger<Engine>.Instance, TimeProvider.System)
            .RunAsync(new RunOptions(), outcomes, CancellationToken.None);
        return (result, outcomes);
    }

    private static async Task<RunResult> Run(EngineSettings settings, FakeRemote remote, FakeSource source) =>
        (await RunWithOutcomes(settings, remote, source)).Result;

    private static JsonDocument ManifestOf(FakeRemote remote) => JsonDocument.Parse(remote.Files["/upload/scans/manifest.json"]);

    [TestMethod]
    public async Task PartThenRename_to_a_new_name_works_on_a_write_only_server()
    {
        var remote = new FakeRemote { WriteOnly = true };

        var result = await Run(Settings(UploadStrategy.PartThenRename), remote, new FakeSource("scans").Add("a.txt", "alpha"));

        Assert.AreEqual(ExitCodes.Ok, result.ExitCode, result.Reason);
        Assert.AreEqual("alpha", remote.ReadText("/upload/scans/a.txt"));
        Assert.IsFalse(remote.Files.ContainsKey("/upload/scans/a.txt.part"));
    }

    [TestMethod]
    public async Task A_refused_rename_over_an_existing_file_is_Failed_with_RemoteDenied_and_the_part_file_is_left()
    {
        var remote = new FakeRemote { WriteOnly = true };
        var settings = Settings(UploadStrategy.PartThenRename);
        await Run(settings, remote, new FakeSource("scans").Add("a.txt", "alpha"));
        var renamesBefore = remote.Operations.Count(o => o.Operation == RemoteOperation.Rename && o.Path.Contains("a.txt"));

        var (result, files) = await RunWithOutcomes(settings, remote, new FakeSource("scans").Add("a.txt", "changed content"));

        Assert.AreEqual(ExitCodes.SomeFilesFailed, result.ExitCode);
        var failed = files.Of("a.txt");
        Assert.AreEqual(FileOutcome.Failed, failed.Outcome);
        StringAssert.StartsWith(failed.Reason, "RemoteDenied");
        Assert.AreEqual("alpha", remote.ReadText("/upload/scans/a.txt"), "the earlier delivery is untouched");
        var left = remote.Files.Where(f => f.Key.StartsWith("/upload/scans/a.txt.", StringComparison.Ordinal) && f.Key.EndsWith(".part", StringComparison.Ordinal)).ToList();
        Assert.HasCount(1, left, "stale .part files are never deleted");
        Assert.AreEqual("changed content", System.Text.Encoding.UTF8.GetString(left[0].Value));
        Assert.AreEqual(renamesBefore + 1, remote.Operations.Count(o => o.Operation == RemoteOperation.Rename && o.Path.Contains("a.txt")),
            "RemoteDenied is permanent: no retry, no fallback");
    }

    [TestMethod]
    public async Task Direct_writes_straight_to_the_final_name_and_the_Manifest_marks_the_file_directUpload()
    {
        var remote = new FakeRemote { WriteOnly = true };

        var result = await Run(Settings(UploadStrategy.Direct), remote, new FakeSource("scans").Add("a.txt", "alpha").Add("b/c.txt", "gamma"));

        Assert.AreEqual(ExitCodes.Ok, result.ExitCode, result.Reason);
        Assert.AreEqual("alpha", remote.ReadText("/upload/scans/a.txt"));
        Assert.IsFalse(remote.Operations.Any(o => o.Operation == RemoteOperation.Rename && !o.Path.Contains("manifest")), "no rename for data files");
        Assert.IsFalse(remote.Operations.Any(o => o.Operation == RemoteOperation.Upload && o.Path.EndsWith("a.txt.part")));
        using var doc = ManifestOf(remote);
        var members = doc.RootElement.GetProperty("members").EnumerateArray().ToList();
        Assert.IsTrue(members.All(m => m.GetProperty("directUpload").GetBoolean()), "every Direct file is marked in the flat members");
        var tree = doc.RootElement.GetProperty("root").GetProperty("children").EnumerateArray().First(c => c.GetProperty("name").GetString() == "a.txt");
        Assert.IsTrue(tree.GetProperty("directUpload").GetBoolean());
    }

    [TestMethod]
    public async Task Direct_is_marked_in_the_Manifest_also_without_an_Upload_State()
    {
        var remote = new FakeRemote { WriteOnly = true };
        var settings = Settings(UploadStrategy.Direct) with { State = new StateSettings() };

        await Run(settings, remote, new FakeSource("scans").Add("a.txt", "alpha"));

        using var doc = ManifestOf(remote);
        Assert.IsTrue(doc.RootElement.GetProperty("members")[0].GetProperty("directUpload").GetBoolean());
    }

    [TestMethod]
    public async Task PartThenRename_files_carry_no_directUpload_mark()
    {
        var remote = new FakeRemote { WriteOnly = true };

        await Run(Settings(UploadStrategy.PartThenRename), remote, new FakeSource("scans").Add("a.txt", "alpha"));

        using var doc = ManifestOf(remote);
        Assert.IsFalse(doc.RootElement.GetProperty("members")[0].TryGetProperty("directUpload", out _));
    }

    [TestMethod]
    public async Task Direct_re_upload_of_a_changed_file_is_Failed_with_RemoteDenied_on_a_server_that_refuses_to_overwrite()
    {
        var remote = new FakeRemote { WriteOnly = true };
        var settings = Settings(UploadStrategy.Direct);
        await Run(settings, remote, new FakeSource("scans").Add("a.txt", "alpha"));

        var (_, files) = await RunWithOutcomes(settings, remote, new FakeSource("scans").Add("a.txt", "changed content"));

        var failed = files.Of("a.txt");
        Assert.AreEqual(FileOutcome.Failed, failed.Outcome);
        StringAssert.StartsWith(failed.Reason, "RemoteDenied");
        Assert.AreEqual("alpha", remote.ReadText("/upload/scans/a.txt"));
    }

    [TestMethod]
    public async Task Direct_verification_looks_at_the_file_itself_not_a_part_file()
    {
        var remote = new FakeRemote();
        var settings = Settings(UploadStrategy.Direct, RemoteAccess.ReadWrite, new VerificationSettings { AfterUpload = VerificationLevel.Size });

        var result = await Run(settings, remote, new FakeSource("scans").Add("a.txt", "alpha"));

        Assert.AreEqual(ExitCodes.Ok, result.ExitCode, result.Reason);
        Assert.AreEqual(1, result.Verified);
        Assert.IsTrue(remote.Operations.Any(o => o.Operation == RemoteOperation.Stat && o.Path == "/upload/scans/a.txt"));
        Assert.IsFalse(remote.Operations.Any(o => o.Path.EndsWith(".part") && o.Path.Contains("a.txt")));
    }

    [TestMethod]
    public async Task Direct_removes_the_final_file_when_verification_fails()
    {
        var remote = new FakeRemote();
        remote.CorruptNextUpload("a.txt", truncate: true, times: 2);
        var settings = Settings(UploadStrategy.Direct, RemoteAccess.ReadWrite, new VerificationSettings { AfterUpload = VerificationLevel.Size });

        var result = await Run(settings, remote, new FakeSource("scans").Add("a.txt", "alpha"));

        Assert.AreEqual(ExitCodes.SomeFilesFailed, result.ExitCode);
        Assert.IsFalse(remote.Files.ContainsKey("/upload/scans/a.txt"), "a bad file must not stay under its final name");
    }

    [TestMethod]
    public async Task Direct_never_deletes_a_previously_delivered_file_when_the_new_version_fails_verification()
    {
        var remote = new FakeRemote();
        var settings = Settings(UploadStrategy.Direct, RemoteAccess.ReadWrite, new VerificationSettings { AfterUpload = VerificationLevel.Size });
        await Run(settings, remote, new FakeSource("scans").Add("a.txt", "alpha"));
        remote.CorruptNextUpload("a.txt", truncate: true, times: 2);

        var result = await Run(settings, remote, new FakeSource("scans").Add("a.txt", "changed content", new DateTimeOffset(2026, 5, 5, 0, 0, 0, TimeSpan.Zero)));

        Assert.AreEqual(ExitCodes.SomeFilesFailed, result.ExitCode);
        Assert.IsTrue(remote.Files.ContainsKey("/upload/scans/a.txt"), "the file the Upload State and the Manifest list is not deleted by the tool");
        using var doc = ManifestOf(remote);
        Assert.IsFalse(doc.RootElement.GetProperty("complete").GetBoolean());
        Assert.AreEqual("a.txt", doc.RootElement.GetProperty("failures")[0].GetProperty("path").GetString());
    }

    [TestMethod]
    public async Task Direct_never_deletes_a_previously_delivered_file_that_changes_while_it_is_read()
    {
        var remote = new FakeRemote();
        var settings = Settings(UploadStrategy.Direct, RemoteAccess.ReadWrite);
        await Run(settings, remote, new FakeSource("scans").Add("a.txt", "alpha"));
        var source = new FakeSource("scans").Add("a.txt", "second version", new DateTimeOffset(2026, 5, 5, 0, 0, 0, TimeSpan.Zero));
        source.AfterOpen = _ => source.Add("a.txt", "third version, still being written", new DateTimeOffset(2026, 6, 6, 0, 0, 0, TimeSpan.Zero));

        var result = await Run(settings, remote, source);

        Assert.AreEqual(ExitCodes.SomeFilesFailed, result.ExitCode);
        Assert.IsTrue(remote.Files.ContainsKey("/upload/scans/a.txt"));
        StringAssert.Contains(remote.ReadText("/upload/scans/manifest.json"), "ChangedDuringUpload");
    }

    [TestMethod]
    public async Task Direct_also_applies_to_Archives()
    {
        var remote = new FakeRemote { WriteOnly = true };
        var archive = new ArchiveConfig
        {
            Rules = [new ArchiveRuleConfig { Name = "docs", Pattern = "^docs/.*", Grouping = ArchiveGrouping.PerRule, ArchiveName = "docs.zip" }],
        };
        var source = new FakeSource("scans").Add("docs/a.txt", "alpha").Add("docs/b.txt", "beta");

        var result = await Run(Settings(UploadStrategy.Direct, archive: archive), remote, source);

        Assert.AreEqual(ExitCodes.Ok, result.ExitCode, result.Reason);
        Assert.IsTrue(remote.Files.ContainsKey("/upload/scans/docs.zip"));
        Assert.IsFalse(remote.Operations.Any(o => o.Path.EndsWith("docs.zip.part")));
        using var doc = ManifestOf(remote);
        Assert.IsTrue(ManifestTree.Archives(doc.RootElement)["docs.zip"].GetProperty("directUpload").GetBoolean());
    }
}

using System.Text.Json;
using Microsoft.Extensions.Logging;
using MiresSftpUploader.Core;
using MiresSftpUploader.Test.Support;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class VerificationTests
{
    private string _dir = "";

    [TestInitialize]
    public void Setup() => _dir = Directory.CreateTempSubdirectory("mires-verify-").FullName;

    [TestCleanup]
    public void Cleanup()
    {
        try { Directory.Delete(_dir, recursive: true); } catch (IOException) { }
    }

    private EngineSettings Settings(VerificationLevel after = VerificationLevel.Off, VerificationLevel remote = VerificationLevel.Off,
        TimeSpan? timeout = null, int attempts = 3, bool withState = false, string command = UploadConfig.DefaultVerifyCommand) => new()
    {
        RemoteRoot = "/upload",
        Destination = "sftp.example:22",
        Retry = new RetrySettings { MaxAttempts = attempts, BaseDelay = TimeSpan.Zero, MaxDelay = TimeSpan.Zero },
        State = withState ? new StateSettings { AccessGroup = TestAccessGroup.Name, Path = Path.Combine(_dir, "data", "state.db") } : new StateSettings(),
        Archive = new ArchiveConfig { StagingPath = Path.Combine(_dir, "staging") },
        Verification = new VerificationSettings
        {
            AfterUpload = after,
            Remote = remote,
            Command = command,
            Timeout = timeout ?? TimeSpan.FromHours(1),
        },
    };

    private static async Task<(RunResult Result, List<RunEvent> Events, CapturingLoggerProvider Log)> RunAsync(
        EngineSettings settings, FakeRemote remote, params ISource[] sources)
    {
        var log = new CapturingLoggerProvider();
        using var factory = LoggerFactory.Create(b => b.AddProvider(log));
        var events = new List<RunEvent>();
        var result = await new Engine(remote, sources, settings, factory.CreateLogger<Engine>(), TimeProvider.System)
            .RunAsync(new RunOptions(), new ListProgress(events), CancellationToken.None);
        return (result, events, log);
    }

    private sealed class ListProgress(List<RunEvent> events) : IProgress<RunEvent>
    {
        public void Report(RunEvent value) { lock (events) events.Add(value); }
    }

    private static byte[] Payload() => [1, 2, 3, 4, 5, 6, 7, 8];

    // ---- after upload ----

    [TestMethod]
    [DataRow(VerificationLevel.Size, true)]
    [DataRow(VerificationLevel.Hash, false)]
    [DataRow(VerificationLevel.ReadBack, false)]
    public async Task A_damaged_upload_is_caught_before_the_rename_and_a_retry_delivers_the_file(VerificationLevel level, bool truncate)
    {
        var remote = new FakeRemote();
        remote.CorruptNextUpload("a.bin", truncate);
        var source = new FakeSource("scans").Add("a.bin", Payload());

        var (result, events, _) = await RunAsync(Settings(level), remote, source);

        Assert.AreEqual(0, result.ExitCode);
        Assert.AreEqual(1, result.Count(FileOutcome.Succeeded));
        CollectionAssert.AreEqual(Payload(), remote.Files["/upload/scans/a.bin"]);
        Assert.IsFalse(remote.Files.Keys.Any(k => k.EndsWith(".part")));
        Assert.AreEqual(2, events.OfType<FileOutcomeChanged>().Count(e => e.Outcome == FileOutcome.Verifying), "one failed and one passed verification");
        Assert.AreEqual(1, result.Verified);
        Assert.AreEqual(0, result.VerificationFailures);
    }

    [TestMethod]
    public async Task A_file_that_never_verifies_is_Failed_with_VerificationFailed_and_never_appears_under_its_final_name()
    {
        var remote = new FakeRemote();
        remote.CorruptNextUpload("bad.bin", times: 10);
        var source = new FakeSource("scans").Add("bad.bin", Payload()).Add("good.bin", Payload());

        var (result, events, _) = await RunAsync(Settings(VerificationLevel.Hash), remote, source);

        Assert.AreEqual(ExitCodes.SomeFilesFailed, result.ExitCode);
        Assert.AreEqual(1, result.Count(FileOutcome.Failed));
        Assert.AreEqual(1, result.Count(FileOutcome.Succeeded));
        Assert.IsFalse(remote.Files.ContainsKey("/upload/scans/bad.bin"));
        Assert.IsFalse(remote.Files.Keys.Any(k => k.EndsWith(".part")), "the .part is deleted");
        var failed = events.OfType<FileOutcomeChanged>().Last(e => e.Outcome == FileOutcome.Failed);
        StringAssert.StartsWith(failed.Reason, "VerificationFailed");
        Assert.AreEqual(1, result.Verified);
        Assert.AreEqual(1, result.VerificationFailures);
        using var manifest = JsonDocument.Parse(remote.ReadText("/upload/scans/manifest.json"));
        var failure = manifest.RootElement.GetProperty("failures").EnumerateArray().Single();
        Assert.AreEqual("bad.bin", failure.GetProperty("path").GetString());
        StringAssert.StartsWith(failure.GetProperty("reason").GetString(), "VerificationFailed");
    }

    [TestMethod]
    public async Task Verification_off_runs_no_command_and_has_no_Verifying_outcome()
    {
        var remote = new FakeRemote();
        var source = new FakeSource("scans").Add("a.bin", Payload());

        var (result, events, _) = await RunAsync(Settings(), remote, source);

        Assert.AreEqual(0, remote.Commands.Count);
        Assert.IsFalse(events.OfType<FileOutcomeChanged>().Any(e => e.Outcome == FileOutcome.Verifying));
        Assert.AreEqual(0, result.Verified);
    }

    [TestMethod]
    public async Task Hash_runs_the_command_on_the_part_file_before_the_rename()
    {
        var remote = new FakeRemote();
        var source = new FakeSource("scans").Add("my file.bin", Payload());

        await RunAsync(Settings(VerificationLevel.Hash), remote, source);

        CollectionAssert.Contains(remote.Commands.ToList(), "sha256sum -- '/upload/scans/my file.bin.part'");
    }

    [TestMethod]
    public async Task A_verification_that_exceeds_the_timeout_fails_the_file()
    {
        var remote = new FakeRemote { CommandDelay = TimeSpan.FromSeconds(30) };
        var source = new FakeSource("scans").Add("slow.bin", Payload());

        var (result, events, _) = await RunAsync(Settings(VerificationLevel.Hash, timeout: TimeSpan.FromMilliseconds(200), attempts: 1), remote, source);

        Assert.AreEqual(1, result.Count(FileOutcome.Failed));
        var failed = events.OfType<FileOutcomeChanged>().Last(e => e.Outcome == FileOutcome.Failed);
        StringAssert.StartsWith(failed.Reason, "VerificationFailed");
        StringAssert.Contains(failed.Reason, "timed out");
        Assert.IsFalse(remote.Files.ContainsKey("/upload/scans/slow.bin"));
    }

    // ---- probe ----

    [TestMethod]
    public async Task Hash_on_a_server_without_a_command_channel_exits_2_before_uploading_anything()
    {
        var remote = new FakeRemote { CommandChannel = false };
        var source = new FakeSource("scans").Add("a.bin", Payload());

        var (result, _, _) = await RunAsync(Settings(VerificationLevel.Hash), remote, source);

        Assert.AreEqual(ExitCodes.ConfigurationError, result.ExitCode);
        StringAssert.Contains(result.Reason, "Hash");
        StringAssert.Contains(result.Reason, "no command channel");
        Assert.AreEqual(0, remote.Files.Count, "nothing was uploaded and the level was not downgraded");
    }

    [TestMethod]
    public async Task A_verify_command_the_server_does_not_have_exits_2()
    {
        var remote = new FakeRemote();
        var source = new FakeSource("scans").Add("a.bin", Payload());

        var (result, _, _) = await RunAsync(Settings(VerificationLevel.Hash, command: "shasum -a 256 {path}"), remote, source);

        Assert.AreEqual(ExitCodes.ConfigurationError, result.ExitCode);
        StringAssert.Contains(result.Reason, "command not found");
    }

    [TestMethod]
    [DataRow(VerificationLevel.Size)]
    [DataRow(VerificationLevel.ReadBack)]
    public async Task Size_and_ReadBack_need_read_access_and_exit_2_without_it(VerificationLevel level)
    {
        var remote = new FakeRemote();
        remote.Inject(RemoteOperation.Stat, RemoteResult.Denied("permission denied"), times: 100);
        var source = new FakeSource("scans").Add("a.bin", Payload());

        var (result, _, _) = await RunAsync(Settings(level), remote, source);

        Assert.AreEqual(ExitCodes.ConfigurationError, result.ExitCode);
        StringAssert.Contains(result.Reason, level.ToString());
        StringAssert.Contains(result.Reason, "permission denied");
        Assert.AreEqual(0, remote.Files.Count);
    }

    [TestMethod]
    public async Task VerifyRemote_alone_is_probed_too()
    {
        var remote = new FakeRemote { CommandChannel = false };
        var source = new FakeSource("scans").Add("a.bin", Payload());

        var (result, _, _) = await RunAsync(Settings(remote: VerificationLevel.Hash), remote, source);

        Assert.AreEqual(ExitCodes.ConfigurationError, result.ExitCode);
        StringAssert.Contains(result.Reason, "VerifyRemote");
    }

    // ---- VerifyRemote ----

    private async Task<FakeSource> FirstRunAsync(FakeRemote remote, VerificationLevel remoteLevel)
    {
        var source = new FakeSource("scans").Add("a.bin", Payload());
        var (result, _, _) = await RunAsync(Settings(remote: remoteLevel, withState: true), remote, source);
        Assert.AreEqual(0, result.ExitCode, result.Reason);
        return source;
    }

    [TestMethod]
    [DataRow(VerificationLevel.Size)]
    [DataRow(VerificationLevel.Hash)]
    [DataRow(VerificationLevel.ReadBack)]
    public async Task VerifyRemote_skips_an_unchanged_file_whose_remote_copy_matches(VerificationLevel level)
    {
        var remote = new FakeRemote();
        var source = await FirstRunAsync(remote, level);

        var (result, _, _) = await RunAsync(Settings(remote: level, withState: true), remote, source);

        Assert.AreEqual(1, result.Count(FileOutcome.Skipped));
        Assert.AreEqual(0, result.Count(FileOutcome.Succeeded));
        Assert.AreEqual(1, result.Verified);
    }

    [TestMethod]
    [DataRow(VerificationLevel.Size)]
    [DataRow(VerificationLevel.Hash)]
    [DataRow(VerificationLevel.ReadBack)]
    public async Task VerifyRemote_uploads_an_unchanged_file_again_when_the_remote_copy_is_missing_and_logs_why(VerificationLevel level)
    {
        var remote = new FakeRemote();
        var source = await FirstRunAsync(remote, level);
        remote.Files.Keys.Where(k => k.EndsWith("a.bin")).ToList().ForEach(k => remote.RemoveFile(k));

        var (result, _, log) = await RunAsync(Settings(remote: level, withState: true), remote, source);

        Assert.AreEqual(1, result.Count(FileOutcome.Succeeded));
        CollectionAssert.AreEqual(Payload(), remote.Files["/upload/scans/a.bin"]);
        Assert.IsTrue(log.Entries.Any(e => e.Message.Contains("a.bin") && e.Message.Contains("missing")), "the reason is logged");
    }

    [TestMethod]
    [DataRow(VerificationLevel.Hash, false)]
    [DataRow(VerificationLevel.ReadBack, false)]
    [DataRow(VerificationLevel.Size, true)]
    public async Task VerifyRemote_uploads_an_unchanged_file_again_when_the_remote_copy_differs_and_logs_why(VerificationLevel level, bool differentSize)
    {
        var remote = new FakeRemote();
        var source = await FirstRunAsync(remote, level);
        var damaged = Payload();
        if (differentSize) damaged = damaged[..^1]; else damaged[0] ^= 0xFF;
        remote.PutFile("/upload/scans/a.bin", damaged);

        var (result, _, log) = await RunAsync(Settings(remote: level, withState: true), remote, source);

        Assert.AreEqual(1, result.Count(FileOutcome.Succeeded));
        CollectionAssert.AreEqual(Payload(), remote.Files["/upload/scans/a.bin"]);
        Assert.IsTrue(log.Entries.Any(e => e.Message.Contains("a.bin") && e.Message.Contains("differs")), "the reason is logged");
    }

    [TestMethod]
    public async Task VerifyRemote_off_trusts_the_upload_state()
    {
        var remote = new FakeRemote();
        var source = await FirstRunAsync(remote, VerificationLevel.Off);
        remote.RemoveFile("/upload/scans/a.bin");

        var (result, _, _) = await RunAsync(Settings(withState: true), remote, source);

        Assert.AreEqual(1, result.Count(FileOutcome.Skipped));
        Assert.IsFalse(remote.Files.ContainsKey("/upload/scans/a.bin"));
    }

    // ---- reporting ----

    [TestMethod]
    public async Task The_Report_counts_verified_files_and_verification_failures()
    {
        var remote = new FakeRemote();
        remote.CorruptNextUpload("bad.bin", times: 10);
        var source = new FakeSource("scans").Add("bad.bin", Payload()).Add("good.bin", Payload());
        var reportPath = Path.Combine(_dir, "report.json");
        var log = new CapturingLoggerProvider();
        using var factory = LoggerFactory.Create(b => b.AddProvider(log));

        await new Engine(remote, [source], Settings(VerificationLevel.Hash), factory.CreateLogger<Engine>(), TimeProvider.System)
            .RunAsync(new RunOptions { ReportPath = reportPath }, new Progress<RunEvent>(), CancellationToken.None);

        using var report = JsonDocument.Parse(File.ReadAllText(reportPath));
        var text = report.RootElement.ToString();
        StringAssert.Contains(text, "Verified");
        StringAssert.Contains(text, "VerificationFailed");
    }

    [TestMethod]
    public void The_headless_summary_shows_verification_counts_only_when_verification_took_place()
    {
        var counts = new Dictionary<FileOutcome, int> { [FileOutcome.Succeeded] = 3, [FileOutcome.Failed] = 1 };

        var with = HeadlessSummary.Format(new RunResult(Guid.Empty, counts, 1, null, Verified: 3, VerificationFailures: 1), null);
        var without = HeadlessSummary.Format(new RunResult(Guid.Empty, counts, 1, null), null);

        Assert.AreEqual("succeeded=3 skipped=0 failed=1 exit=1 report=- verified=3 verification_failed=1", with);
        Assert.AreEqual("succeeded=3 skipped=0 failed=1 exit=1 report=-", without);
    }

    // ---- Archives ----

    [TestMethod]
    public async Task An_Archive_is_verified_the_same_way()
    {
        var remote = new FakeRemote();
        remote.CorruptNextUpload("tiles", times: 10);
        var source = new FakeSource("scans").Add("slide/t1.jpg", "t1").Add("slide/t2.jpg", "t2");
        var settings = Settings(VerificationLevel.Hash, attempts: 2) with
        {
            Archive = new ArchiveConfig
            {
                StagingPath = Path.Combine(_dir, "staging"),
                Rules = [new ArchiveRuleConfig { Name = "tiles", Pattern = @"\.jpg$" }],
            },
        };

        var (result, events, _) = await RunAsync(settings, remote, source);

        Assert.AreEqual(2, result.Count(FileOutcome.Failed));
        StringAssert.StartsWith(events.OfType<FileOutcomeChanged>().Last(e => e.Outcome == FileOutcome.Failed).Reason, "VerificationFailed");
        Assert.IsFalse(remote.Files.Keys.Any(k => k.Contains("tiles")), "no damaged Archive under its final name or as .part");
        Assert.AreEqual(1, result.VerificationFailures);
    }
}

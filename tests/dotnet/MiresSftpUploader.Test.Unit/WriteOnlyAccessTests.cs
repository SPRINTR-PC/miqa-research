using Microsoft.Extensions.Logging;
using MiresSftpUploader.Core;
using MiresSftpUploader.Test.Support;

namespace MiresSftpUploader.Test.Unit;

/// <summary>Write-only Access: the account can upload but not read, list, delete or overwrite.</summary>
[TestClass]
public sealed class WriteOnlyAccessTests
{
    private string _dir = "";

    [TestInitialize]
    public void Setup() => _dir = Directory.CreateTempSubdirectory("mires-writeonly-").FullName;

    [TestCleanup]
    public void Cleanup()
    {
        try { Directory.Delete(_dir, recursive: true); } catch (IOException) { }
    }

    private EngineSettings Settings(RemoteAccess access = RemoteAccess.Auto, UploadStrategy strategy = UploadStrategy.PartThenRename,
        VerificationSettings? verification = null, bool withState = true) => new()
    {
        RemoteRoot = "/upload",
        Destination = "sftp.example:22",
        RemoteAccess = access,
        UploadStrategy = strategy,
        Verification = verification ?? new VerificationSettings(),
        Retry = new RetrySettings { MaxAttempts = 2, BaseDelay = TimeSpan.Zero, MaxDelay = TimeSpan.Zero },
        State = new StateSettings { Path = withState ? Path.Combine(_dir, "state.db") : null },
    };

    private static (Engine Engine, CapturingLoggerProvider Log) NewEngine(EngineSettings settings, FakeRemote remote, params ISource[] sources)
    {
        var log = new CapturingLoggerProvider();
        var factory = LoggerFactory.Create(b => b.SetMinimumLevel(LogLevel.Trace).AddProvider(log));
        return (new Engine(remote, sources, settings, new Logger<Engine>(factory), TimeProvider.System), log);
    }

    private static Task<RunResult> Run(Engine engine, RunOptions? options = null) =>
        engine.RunAsync(options ?? new RunOptions(), new Progress<RunEvent>(), CancellationToken.None);

    [TestMethod]
    public async Task Auto_treats_a_refused_stat_and_listing_as_write_only_and_logs_it()
    {
        var remote = new FakeRemote { WriteOnly = true };
        var (engine, log) = NewEngine(Settings(), remote, new FakeSource("scans").Add("a.txt", "alpha"));

        var result = await Run(engine);

        Assert.AreEqual(ExitCodes.Ok, result.ExitCode, result.Reason);
        Assert.AreEqual("alpha", remote.ReadText("/upload/scans/a.txt"));
        Assert.IsTrue(log.Entries.Any(e => e.Level == LogLevel.Information && e.Message.Contains("write-only", StringComparison.OrdinalIgnoreCase)), "the probe result is logged");
    }

    [TestMethod]
    public async Task Auto_on_a_readable_server_logs_read_write_and_keeps_the_read_based_checks()
    {
        var remote = new FakeRemote();
        var (engine, log) = NewEngine(Settings(), remote, new FakeSource("scans").Add("manifest.json", "mine"));

        var result = await Run(engine);

        Assert.AreEqual(ExitCodes.ConfigurationError, result.ExitCode, "a Source file named like the Manifest is still refused");
        Assert.IsTrue(log.Entries.Any(e => e.Message.Contains("read-write", StringComparison.OrdinalIgnoreCase)), "the probe result is logged");
    }

    [TestMethod]
    public async Task A_write_only_Run_reads_nothing_from_the_server()
    {
        var remote = new FakeRemote { WriteOnly = true };
        var (engine, _) = NewEngine(Settings(RemoteAccess.WriteOnly), remote, new FakeSource("scans").Add("a.txt", "alpha").Add("b/c.txt", "gamma"));

        await Run(engine);

        var reads = remote.Operations.Where(o => o.Operation is RemoteOperation.Stat or RemoteOperation.List or RemoteOperation.Download
            or RemoteOperation.RunCommand or RemoteOperation.Delete).ToList();
        Assert.IsEmpty(reads, string.Join(", ", reads));
    }

    [TestMethod]
    public async Task Write_only_skips_the_Manifest_name_collision_check()
    {
        var remote = new FakeRemote { WriteOnly = true };
        var (engine, _) = NewEngine(Settings(RemoteAccess.WriteOnly), remote, new FakeSource("scans").Add("manifest.json", "mine"));

        var result = await Run(engine);

        Assert.AreEqual(ExitCodes.Ok, result.ExitCode, result.Reason);
    }

    [TestMethod]
    public async Task Write_only_places_no_In_progress_Marker()
    {
        var remote = new FakeRemote { WriteOnly = true };
        var (engine, _) = NewEngine(Settings(RemoteAccess.WriteOnly), remote, new FakeSource("scans").Add("a.txt", "alpha"));

        await Run(engine);

        Assert.IsFalse(remote.Files.Keys.Any(k => k.Contains(".inprogress")), string.Join(", ", remote.Files.Keys));
    }

    [TestMethod]
    [DataRow(RemoteAccess.WriteOnly)]
    [DataRow(RemoteAccess.Auto)]
    public async Task Verification_with_write_only_access_exits_2_before_anything_is_uploaded(RemoteAccess access)
    {
        var remote = new FakeRemote { WriteOnly = true };
        var settings = Settings(access, verification: new VerificationSettings { AfterUpload = VerificationLevel.Size });
        var (engine, _) = NewEngine(settings, remote, new FakeSource("scans").Add("a.txt", "alpha"));

        var result = await Run(engine);

        Assert.AreEqual(ExitCodes.ConfigurationError, result.ExitCode);
        StringAssert.Contains(result.Reason, "write-only", StringComparison.OrdinalIgnoreCase);
        Assert.IsEmpty(remote.Files);
    }

    [TestMethod]
    public async Task Auto_that_cannot_prepare_the_remote_root_fails_the_Run_instead_of_assuming_read_write()
    {
        var remote = new FakeRemote();
        remote.Inject(RemoteOperation.EnsureDirectory, RemoteResult.Failed("connection reset"), times: 1, pathContains: "/upload");
        var (engine, _) = NewEngine(Settings(), remote, new FakeSource("scans").Add("a.txt", "alpha"));

        var result = await Run(engine);

        Assert.AreEqual(ExitCodes.ConnectFailed, result.ExitCode);
        StringAssert.Contains(result.Reason, "connection reset");
        StringAssert.Contains(result.Reason, "RemoteAccess");
        Assert.IsEmpty(remote.Files);
    }

    [TestMethod]
    public async Task Auto_that_is_refused_the_remote_root_exits_2_and_says_to_set_RemoteAccess()
    {
        var remote = new FakeRemote();
        remote.Inject(RemoteOperation.EnsureDirectory, RemoteResult.Denied("permission denied"), times: 1, pathContains: "/upload");
        var (engine, _) = NewEngine(Settings(), remote, new FakeSource("scans").Add("a.txt", "alpha"));

        var result = await Run(engine);

        Assert.AreEqual(ExitCodes.ConfigurationError, result.ExitCode);
        StringAssert.Contains(result.Reason, "RemoteAccess");
        Assert.IsEmpty(remote.Files);
    }

    [TestMethod]
    [DataRow(RemoteOperation.Stat)]
    [DataRow(RemoteOperation.List)]
    public async Task Auto_whose_probe_fails_for_a_reason_other_than_a_refusal_fails_the_Run(RemoteOperation failing)
    {
        var remote = new FakeRemote();
        remote.Inject(failing, RemoteResult.Failed("i/o error"), times: 1, pathContains: "/upload");
        var (engine, _) = NewEngine(Settings(), remote, new FakeSource("scans").Add("a.txt", "alpha"));

        var result = await Run(engine);

        Assert.AreEqual(ExitCodes.ConnectFailed, result.ExitCode);
        StringAssert.Contains(result.Reason, "i/o error");
        Assert.IsEmpty(remote.Files);
    }

    [TestMethod]
    public async Task A_retry_after_a_mid_upload_cut_succeeds_on_a_server_that_cannot_replace_the_part_file()
    {
        var remote = new FakeRemote { WriteOnly = true };
        remote.CutNextUpload(".part", times: 1);
        var (engine, _) = NewEngine(Settings(RemoteAccess.WriteOnly), remote, new FakeSource("scans").Add("a.txt", "alpha"));

        var result = await Run(engine);

        Assert.AreEqual(ExitCodes.Ok, result.ExitCode, result.Reason);
        Assert.AreEqual("alpha", remote.ReadText("/upload/scans/a.txt"));
    }

    [TestMethod]
    public async Task A_part_file_left_by_an_earlier_Run_does_not_block_a_write_only_upload()
    {
        var remote = new FakeRemote { WriteOnly = true };
        remote.PutFile("/upload/scans/a.txt.part", "half"u8.ToArray());
        var (engine, _) = NewEngine(Settings(RemoteAccess.WriteOnly), remote, new FakeSource("scans").Add("a.txt", "alpha"));

        var result = await Run(engine);

        Assert.AreEqual(ExitCodes.Ok, result.ExitCode, result.Reason);
        Assert.AreEqual("alpha", remote.ReadText("/upload/scans/a.txt"));
    }

    [TestMethod]
    public async Task On_a_readable_server_the_part_file_name_stays_predictable()
    {
        var remote = new FakeRemote();
        var (engine, _) = NewEngine(Settings(RemoteAccess.ReadWrite), remote, new FakeSource("scans").Add("a.txt", "alpha"));

        await Run(engine);

        Assert.IsTrue(remote.Operations.Any(o => o.Operation == RemoteOperation.Upload && o.Path == "/upload/scans/a.txt.part"));
    }

    [TestMethod]
    public async Task A_Dry_Run_does_not_touch_the_server_to_probe_access()
    {
        var remote = new FakeRemote { WriteOnly = true };
        var (engine, _) = NewEngine(Settings(), remote, new FakeSource("scans").Add("a.txt", "alpha"));

        await Run(engine, new RunOptions { DryRun = true });

        Assert.IsEmpty(remote.Operations);
    }
}

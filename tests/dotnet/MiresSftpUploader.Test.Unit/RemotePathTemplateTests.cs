using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Time.Testing;
using MiresSftpUploader.Core;
using MiresSftpUploader.Test.Support;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class RemotePathTemplateTests
{
    private string _dir = "";

    [TestInitialize]
    public void Setup() => _dir = Directory.CreateTempSubdirectory("mires-remote-template-").FullName;

    [TestCleanup]
    public void Cleanup()
    {
        try { Directory.Delete(_dir, recursive: true); } catch (IOException) { }
    }

    private static readonly DateTimeOffset Day1 = new(2026, 3, 7, 23, 59, 30, TimeSpan.Zero);

    [TestMethod]
    public void The_placeholders_are_replaced_with_the_UTC_start_of_the_Run()
    {
        var local = new DateTimeOffset(2026, 3, 8, 1, 5, 9, TimeSpan.FromHours(2)); // 23:05:09 UTC on the 7th

        Assert.AreEqual("/in/20260307/230509/2026/03/07", RemotePathTemplate.Expand("/in/{date}/{time}/{year}/{month}/{day}", local));
        Assert.AreEqual("/plain", RemotePathTemplate.Expand("/plain", local));
    }

    [TestMethod]
    public void Unknown_placeholders_and_lone_braces_are_found()
    {
        CollectionAssert.AreEqual(new[] { "{dat}" }, RemotePathTemplate.Unknown("/in/{date}/{dat}").ToArray());
        CollectionAssert.AreEqual(new[] { "a lone { or }" }, RemotePathTemplate.Unknown("/in/{date").ToArray());
        Assert.IsEmpty(RemotePathTemplate.Unknown("/in/{date}/{year}"));
    }

    private static List<ConfigError> Validate(AppConfig config)
    {
        var errors = new List<ConfigError>();
        ConfigValidator.Validate(config, headless: false, errors, []);
        return errors;
    }

    [TestMethod]
    [DataRow("Sftp:RemoteRoot", "/incoming/{dat}", "unknown placeholder {dat}")]
    [DataRow("Sftp:RemoteRoot", "/incoming/{date", "lone")]
    [DataRow("Sftp:RemoteRoot", "incoming/{date}", "absolute POSIX path")]
    [DataRow("Sftp:RemoteRoot", "/incoming/../{date}", "absolute POSIX path")]
    public void The_validator_rejects_bad_templates(string key, string value, string expected)
    {
        var config = new AppConfig { Sftp = new SftpConfig { Host = "h", Username = "u", HostKeyFingerprint = "fp", RemoteRoot = value } };

        var errors = Validate(config).Where(e => e.Key == key).ToList();

        Assert.HasCount(1, errors);
        StringAssert.Contains(errors[0].Message, expected);
    }

    [TestMethod]
    public void The_validator_accepts_known_placeholders_in_the_root_and_in_a_Source_path()
    {
        var config = new AppConfig
        {
            Sftp = new SftpConfig { Host = "h", Username = "u", HostKeyFingerprint = "fp", RemoteRoot = "/in/{year}/{month}/{day}" },
            Sources = [new SourceConfig { Name = "s", Path = "/data", RemotePath = "/drop/{date}-{time}" }],
        };

        Assert.IsFalse(Validate(config).Any(e => e.Key is "Sftp:RemoteRoot" or "Sources:0:RemotePath"));
    }

    private EngineSettings Settings(string root) => new()
    {
        RemoteRoot = root,
        Destination = "sftp.example:22",
        Retry = new RetrySettings { MaxAttempts = 1, BaseDelay = TimeSpan.Zero, MaxDelay = TimeSpan.Zero },
        State = new StateSettings { AccessGroup = TestAccessGroup.Name, Path = Path.Combine(_dir, "state.db") },
    };

    private static Task<RunResult> Run(EngineSettings settings, FakeRemote remote, FakeSource source, TimeProvider time, RunOptions? options = null) =>
        new Engine(remote, [source], settings, NullLogger<Engine>.Instance, time)
            .RunAsync(options ?? new RunOptions(), new Progress<RunEvent>(), CancellationToken.None);

    [TestMethod]
    public async Task The_Remote_Root_gets_a_new_directory_each_day()
    {
        var time = new FakeTimeProvider(Day1);
        var remote = new FakeRemote();
        var source = new FakeSource("scans").Add("a.txt", "alpha");
        var settings = Settings("/incoming/{date}");

        await Run(settings, remote, source, time);
        time.Advance(TimeSpan.FromMinutes(5)); // past midnight
        await Run(settings, remote, source, time);

        Assert.AreEqual("alpha", remote.ReadText("/incoming/20260307/scans/a.txt"));
        Assert.AreEqual("alpha", remote.ReadText("/incoming/20260308/scans/a.txt"));
        Assert.IsFalse(remote.Files.ContainsKey("/incoming/{date}/scans/a.txt"), "no directory is named after the placeholder");
    }

    [TestMethod]
    public async Task A_Source_Remote_Path_takes_the_placeholders_too()
    {
        var time = new FakeTimeProvider(Day1);
        var remote = new FakeRemote();
        var source = new FakeSource("scans", remotePath: "/drop/{year}/{month}/{day}").Add("a.txt", "alpha");

        await Run(Settings("/ignored"), remote, source, time);

        Assert.AreEqual("alpha", remote.ReadText("/drop/2026/03/07/a.txt"));
    }

    [TestMethod]
    public async Task A_retry_uses_the_Remote_Path_of_the_Run_it_repeats_not_todays()
    {
        var time = new FakeTimeProvider(Day1);
        var remote = new FakeRemote();
        var source = new FakeSource("scans").Add("a.txt", "alpha").Add("b.txt", "beta");
        remote.Inject(RemoteOperation.Upload, RemoteResult.Failed("disk full"), pathContains: "b.txt");
        var settings = Settings("/incoming/{date}");
        var first = await Run(settings, remote, source, time);
        Assert.AreEqual(1, first.ExitCode);

        time.Advance(TimeSpan.FromDays(2));
        var retry = await Run(settings, remote, source, time, new RunOptions { RetryOf = first.RunId });

        Assert.AreEqual(0, retry.ExitCode);
        Assert.AreEqual("beta", remote.ReadText("/incoming/20260307/scans/b.txt"));
        Assert.IsFalse(remote.Files.ContainsKey("/incoming/20260309/scans/b.txt"), "the retry did not move to the new day's directory");
    }

    [TestMethod]
    public async Task A_retry_still_finds_its_files_after_the_template_was_changed()
    {
        var time = new FakeTimeProvider(Day1);
        var remote = new FakeRemote();
        var source = new FakeSource("scans").Add("a.txt", "alpha").Add("b.txt", "beta");
        remote.Inject(RemoteOperation.Upload, RemoteResult.Failed("disk full"), pathContains: "b.txt");
        var first = await Run(Settings("/incoming/{date}"), remote, source, time);

        var retry = await Run(Settings("/elsewhere"), remote, source, time, new RunOptions { RetryOf = first.RunId });

        Assert.AreEqual(0, retry.ExitCode);
        Assert.AreEqual("beta", remote.ReadText("/incoming/20260307/scans/b.txt"));
    }
}

using System.Text.Json;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Time.Testing;
using MiresSftpUploader.Core;
using MiresSftpUploader.Test.Support;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class ReportTests
{
    private string _dir = "";

    [TestInitialize]
    public void Setup() => _dir = Directory.CreateTempSubdirectory("mires-report-").FullName;

    [TestCleanup]
    public void Cleanup()
    {
        try { Directory.Delete(_dir, recursive: true); } catch (IOException) { }
    }

    private string DbPath => Path.Combine(_dir, "data", "state.db");

    private EngineSettings Settings(ReportSettings? report = null) => new()
    {
        RemoteRoot = "/upload",
        Destination = "sftp.example:22",
        Retry = new RetrySettings { MaxAttempts = 1, BaseDelay = TimeSpan.Zero, MaxDelay = TimeSpan.Zero },
        State = new StateSettings { Path = DbPath },
        Report = report ?? new ReportSettings(),
    };

    private static Task<RunResult> Run(EngineSettings settings, FakeRemote remote, ISource source, RunOptions? options = null, TimeProvider? time = null) =>
        new Engine(remote, [source], settings, NullLogger<Engine>.Instance, time ?? TimeProvider.System)
            .RunAsync(options ?? new RunOptions(), new Progress<RunEvent>(), CancellationToken.None);

    private string[] ReportFiles(string? directory = null) =>
        Directory.Exists(directory ?? Path.Combine(_dir, "data", "reports"))
            ? Directory.GetFiles(directory ?? Path.Combine(_dir, "data", "reports"))
            : [];

    [TestMethod]
    public async Task Report_path_option_writes_a_json_report_of_the_run()
    {
        var path = Path.Combine(_dir, "out", "report.json");
        var source = new FakeSource("scans").Add("a.txt", "alpha").Add("b.txt", "beta");

        var result = await Run(Settings(), new FakeRemote(), source, new RunOptions { ReportPath = path });

        using var document = JsonDocument.Parse(await File.ReadAllTextAsync(path));
        Assert.AreEqual(result.RunId.ToString(), document.RootElement.GetProperty("run").GetProperty("runId").GetString());
        Assert.AreEqual(0, document.RootElement.GetProperty("run").GetProperty("exitCode").GetInt32());
        Assert.AreEqual(2, document.RootElement.GetProperty("run").GetProperty("counts").GetProperty("Succeeded").GetInt32());
        CollectionAssert.AreEqual(new[] { "a.txt", "b.txt" },
            document.RootElement.GetProperty("files").EnumerateArray().Select(f => f.GetProperty("path").GetString()).ToArray());
    }

    [TestMethod]
    public async Task Report_format_option_picks_csv()
    {
        var path = Path.Combine(_dir, "report.csv");

        await Run(Settings(), new FakeRemote(), new FakeSource("scans").Add("a.txt", "alpha"),
            new RunOptions { ReportPath = path, ReportFormat = ReportFormat.Csv });

        StringAssert.StartsWith(await File.ReadAllTextAsync(path), "RunId,StartedAt,Status,ExitCode,StartedBy,Source,Path,Outcome,");
    }

    [TestMethod]
    public async Task Report_is_written_whatever_the_exit_code()
    {
        var remote = new FakeRemote();
        remote.Inject(RemoteOperation.Upload, RemoteResult.Failed("disk full"), times: 5);
        var failedFiles = await Run(Settings(), remote, new FakeSource("scans").Add("a.txt", "a"));
        var unknownSource = await Run(Settings(), new FakeRemote(), new FakeSource("scans").Add("a.txt", "a"), new RunOptions { SourceNames = ["nope"] });

        Assert.AreEqual(1, failedFiles.ExitCode);
        Assert.AreEqual(2, unknownSource.ExitCode);
        var exitCodes = ReportFiles()
            .Select(f => JsonDocument.Parse(File.ReadAllText(f)).RootElement.GetProperty("run").GetProperty("exitCode").GetInt32())
            .Order().ToArray();
        CollectionAssert.AreEqual(new[] { 1, 2 }, exitCodes);
    }

    [TestMethod]
    public async Task Default_directory_is_reports_beside_the_upload_state_and_the_name_pattern_is_configurable()
    {
        var time = new FakeTimeProvider(new DateTimeOffset(2026, 3, 1, 12, 30, 15, TimeSpan.Zero));
        var settings = Settings(new ReportSettings { FileNamePattern = "report-{date}-{time}-{runId}.{ext}", Format = ReportFormat.Csv });

        var result = await Run(settings, new FakeRemote(), new FakeSource("scans").Add("a.txt", "a"), time: time);

        var file = Assert.ContainsSingle(ReportFiles());
        Assert.AreEqual($"report-20260301-123015-{result.RunId}.csv", Path.GetFileName(file));
    }

    [TestMethod]
    public async Task Report_directory_is_configurable()
    {
        var reports = Path.Combine(_dir, "elsewhere");
        var settings = Settings(new ReportSettings { Directory = reports });

        await Run(settings, new FakeRemote(), new FakeSource("scans").Add("a.txt", "a"));

        Assert.HasCount(1, ReportFiles(reports));
        Assert.IsEmpty(ReportFiles());
    }

    [TestMethod]
    public async Task Dry_run_writes_no_automatic_report_but_honours_an_explicit_path()
    {
        var source = new FakeSource("scans").Add("a.txt", "a");
        await Run(Settings(), new FakeRemote(), source, new RunOptions { DryRun = true });
        Assert.IsEmpty(ReportFiles());

        var path = Path.Combine(_dir, "dry.json");
        await Run(Settings(), new FakeRemote(), source, new RunOptions { DryRun = true, ReportPath = path });

        using var document = JsonDocument.Parse(await File.ReadAllTextAsync(path));
        Assert.AreEqual(1, document.RootElement.GetProperty("run").GetProperty("counts").GetProperty("Pending").GetInt32());
    }

    [TestMethod]
    public async Task Report_is_not_uploaded()
    {
        var remote = new FakeRemote();

        await Run(Settings(), remote, new FakeSource("scans").Add("a.txt", "a"));

        Assert.HasCount(1, ReportFiles());
        CollectionAssert.AreEquivalent(new[] { "/upload/scans/a.txt", "/upload/scans/manifest.json" }, remote.Files.Keys.ToArray());
    }

    [TestMethod]
    public async Task A_report_that_cannot_be_written_does_not_change_the_result()
    {
        var blocker = Path.Combine(_dir, "blocker");
        await File.WriteAllTextAsync(blocker, "a file where the directory should go");

        var result = await Run(Settings(), new FakeRemote(), new FakeSource("scans").Add("a.txt", "a"),
            new RunOptions { ReportPath = Path.Combine(blocker, "report.json") });

        Assert.AreEqual(0, result.ExitCode);
    }

    [TestMethod]
    public async Task On_unix_the_report_is_readable_and_writable_by_the_group_only()
    {
        if (OperatingSystem.IsWindows()) Assert.Inconclusive("Windows permissions come from the inherited ACL of the Data Directory.");

        await Run(Settings(), new FakeRemote(), new FakeSource("scans").Add("a.txt", "a"));

        var mode = File.GetUnixFileMode(Assert.ContainsSingle(ReportFiles()));
        Assert.AreEqual(UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.GroupRead | UnixFileMode.GroupWrite, mode);
    }

    [TestMethod]
    public async Task The_run_records_its_trigger_in_the_history()
    {
        await Run(Settings(), new FakeRemote(), new FakeSource("scans").Add("a.txt", "a"), new RunOptions { Trigger = RunTrigger.Ui });

        var run = new RunHistory(Settings().State, TimeProvider.System).ListRuns().Single();
        Assert.AreEqual("Ui", run.Trigger);
        Assert.AreEqual("Run", run.Mode);
    }
}

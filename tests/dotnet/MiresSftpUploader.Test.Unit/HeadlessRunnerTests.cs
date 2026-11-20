using Microsoft.Extensions.Logging.Abstractions;
using MiresSftpUploader.Core;
using MiresSftpUploader.Test.Support;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class HeadlessRunnerTests : ConfigurationTestBase
{
    private readonly FakeRemote _remote = new();

    /// <summary>A valid configuration whose Data Directory is a folder this account can write.</summary>
    private string Machine()
    {
        var machine = ValidMachine();
        machine["State"] = new System.Text.Json.Nodes.JsonObject { ["Path"] = Path.Combine(Dir, "shared") };
        Directory.CreateDirectory(Path.Combine(Dir, "shared"));
        return machine.ToJsonString();
    }

    private void AddFile()
    {
        Directory.CreateDirectory(DataDir);
        File.WriteAllText(Path.Combine(DataDir, "a.txt"), "alpha");
    }

    private async Task<(int ExitCode, string Out, string Err)> RunAsync(params string[] args)
    {
        File.WriteAllText(MachinePath, Machine());
        var cli = CliOptions.Parse(args).Options!;
        var configuration = new Configuration(new ConfigurationLocations(MachinePath, UserPath, new Dictionary<string, string?>()));
        var runtime = new UploaderRuntime(configuration, new StaticRemoteFactory(_remote), NullLoggerFactory.Instance, TimeProvider.System, cli);
        var stdout = new StringWriter();
        var stderr = new StringWriter();
        var exit = await HeadlessRunner.RunAsync(cli, runtime, stdout, stderr, CancellationToken.None);
        return (exit, stdout.ToString(), stderr.ToString());
    }

    [TestMethod]
    public async Task A_headless_run_uploads_the_configured_Sources_and_prints_only_the_summary_line()
    {
        AddFile();
        var report = Path.Combine(Dir, "out", "report.json");

        var r = await RunAsync("--headless", "--report", report);

        Assert.AreEqual(0, r.ExitCode, r.Err);
        Assert.AreEqual($"succeeded=1 skipped=0 failed=0 exit=0 report={report}{Environment.NewLine}", r.Out);
        Assert.AreEqual("alpha", _remote.ReadText("/incoming/alpha/a.txt"));
        StringAssert.Contains(File.ReadAllText(report), "a.txt");
    }

    [TestMethod]
    public async Task A_headless_Dry_Run_prints_the_zip_plan_on_stderr_and_keeps_stdout_to_the_summary()
    {
        var machine = System.Text.Json.Nodes.JsonNode.Parse(Machine())!.AsObject();
        machine["Archive"] = new System.Text.Json.Nodes.JsonObject
        {
            ["Rules"] = new System.Text.Json.Nodes.JsonArray(new System.Text.Json.Nodes.JsonObject { ["Name"] = "texts", ["Pattern"] = "\\.txt$" }),
        };
        File.WriteAllText(MachinePath, machine.ToJsonString());
        AddFile();
        var cli = CliOptions.Parse(["--headless", "--dry-run"]).Options!;
        var configuration = new Configuration(new ConfigurationLocations(MachinePath, UserPath, new Dictionary<string, string?>()));
        var runtime = new UploaderRuntime(configuration, new StaticRemoteFactory(_remote), NullLoggerFactory.Instance, TimeProvider.System, cli);
        var stdout = new StringWriter();
        var stderr = new StringWriter();

        var exit = await HeadlessRunner.RunAsync(cli, runtime, stdout, stderr, CancellationToken.None);

        Assert.AreEqual(0, exit, stderr.ToString());
        StringAssert.Contains(stderr.ToString(), "archive: ");
        StringAssert.Contains(stderr.ToString(), "rule=texts files=1");
        StringAssert.Contains(stderr.ToString(), "status=WouldBuild");
        Assert.DoesNotContain("archive", stdout.ToString());
    }

    [TestMethod]
    public async Task With_a_status_line_stdout_is_still_exactly_the_summary_line_and_no_status_line_is_left_on_stderr()
    {
        AddFile();
        File.WriteAllText(MachinePath, Machine());
        var cli = CliOptions.Parse(["--headless"]).Options!;
        var configuration = new Configuration(new ConfigurationLocations(MachinePath, UserPath, new Dictionary<string, string?>()));
        var runtime = new UploaderRuntime(configuration, new StaticRemoteFactory(_remote), NullLoggerFactory.Instance, TimeProvider.System, cli);
        var stdout = new StringWriter();
        var stderr = new StringWriter();
        var status = new StatusLineWriter(stderr, () => 80);

        var exit = await HeadlessRunner.RunAsync(cli, runtime, stdout, status, CancellationToken.None, status, NullLoggerFactory.Instance, TimeProvider.System);

        Assert.AreEqual(0, exit, stderr.ToString());
        StringAssert.StartsWith(stdout.ToString(), "succeeded=1 skipped=0 failed=0 exit=0 report=");
        Assert.AreEqual(1, stdout.ToString().TrimEnd().Split('\n').Length, stdout.ToString());
        status.WriteLine("after the run");
        Assert.AreEqual("after the run" + Environment.NewLine, stderr.ToString().Replace("\r", "").TrimStart(' ', '\n'));
    }

    [TestMethod]
    public async Task Dry_run_uploads_nothing()
    {
        AddFile();

        var r = await RunAsync("--headless", "--dry-run");

        Assert.AreEqual(0, r.ExitCode, r.Err);
        Assert.IsEmpty(_remote.Files);
        StringAssert.Contains(r.Out, "report=-");
    }

    [TestMethod]
    public async Task Report_format_flag_selects_the_Report_format()
    {
        AddFile();
        var report = Path.Combine(Dir, "r.csv");

        await RunAsync("--headless", "--report", report, "--report-format", "csv");

        StringAssert.StartsWith(File.ReadAllText(report), "RunId,StartedAt,");
    }

    [TestMethod]
    public async Task Source_flag_runs_only_that_Source_using_the_configured_spelling()
    {
        AddFile();

        var r = await RunAsync("--headless", "--source", "ALPHA");

        Assert.AreEqual(0, r.ExitCode, r.Err);
        Assert.IsTrue(_remote.Files.ContainsKey("/incoming/alpha/a.txt"));
    }

    [TestMethod]
    public async Task A_connection_that_fails_gives_exit_3_with_the_summary_still_the_only_stdout()
    {
        AddFile();
        _remote.Inject(RemoteOperation.Connect, RemoteResult.Failed("refused"), times: 100);

        var r = await RunAsync("--headless");

        Assert.AreEqual(3, r.ExitCode);
        Assert.AreEqual(1, r.Out.TrimEnd().Split('\n').Length);
        StringAssert.Contains(r.Out, "exit=3");
    }

    [TestMethod]
    public async Task The_placeholder_remote_fails_the_run_with_a_clear_message_until_the_SFTP_adapter_is_plugged_in()
    {
        File.WriteAllText(MachinePath, Machine());
        AddFile();
        var cli = CliOptions.Parse(["--headless"]).Options!;
        var configuration = new Configuration(new ConfigurationLocations(MachinePath, UserPath, new Dictionary<string, string?>()));
        var runtime = new UploaderRuntime(configuration, new UnavailableRemoteFactory(), NullLoggerFactory.Instance, TimeProvider.System, cli);
        var stdout = new StringWriter();

        var exit = await HeadlessRunner.RunAsync(cli, runtime, stdout, new StringWriter(), CancellationToken.None);

        Assert.AreEqual(3, exit);
        StringAssert.Contains(stdout.ToString(), "exit=3");
    }

    [TestMethod]
    public async Task An_invalid_configuration_is_listed_on_stderr_with_exit_2_and_nothing_on_stdout()
    {
        File.WriteAllText(MachinePath, "{}");
        var cli = CliOptions.Parse(["--headless"]).Options!;
        var configuration = new Configuration(new ConfigurationLocations(MachinePath, UserPath, new Dictionary<string, string?>()));
        var runtime = new UploaderRuntime(configuration, new StaticRemoteFactory(_remote), NullLoggerFactory.Instance, TimeProvider.System, cli);
        var stdout = new StringWriter();
        var stderr = new StringWriter();

        var exit = await HeadlessRunner.RunAsync(cli, runtime, stdout, stderr, CancellationToken.None);

        Assert.AreEqual(2, exit);
        Assert.AreEqual("", stdout.ToString());
        StringAssert.Contains(stderr.ToString(), "Sftp:Host");
    }
}

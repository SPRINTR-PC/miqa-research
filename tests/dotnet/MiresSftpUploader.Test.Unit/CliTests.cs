using Microsoft.Extensions.Logging.Abstractions;
using MiresSftpUploader.Core;
using MiresSftpUploader.Test.Support;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class CliTests
{
    private static (bool Handled, int ExitCode, string Out, string Err) Invoke(params string[] args)
    {
        var stdout = new StringWriter();
        var stderr = new StringWriter();
        var handled = Cli.TryRun(args, "1.2.3", stdout, stderr, out var exitCode);
        return (handled, exitCode, stdout.ToString(), stderr.ToString());
    }

    private static (bool Handled, int ExitCode, string Out, string Err) InvokeWithState(string databasePath, params string[] args)
    {
        var stdout = new StringWriter();
        var stderr = new StringWriter();
        var handled = Cli.TryRun(args, "1.2.3", stdout, stderr, out var exitCode, state: new StateSettings { AccessGroup = TestAccessGroup.Name, Path = databasePath });
        return (handled, exitCode, stdout.ToString(), stderr.ToString());
    }

    /// <summary>Two Runs in a fresh Upload State: a clean one, then one with a failed file. Returns the database path and run ids.</summary>
    private static async Task<(string Db, Guid Clean, Guid Failing)> TwoRuns()
    {
        var db = Path.Combine(Directory.CreateTempSubdirectory("mires-cli-").FullName, "state.db");
        var settings = new EngineSettings
        {
            RemoteRoot = "/upload", Destination = "h:22",
            Retry = new RetrySettings { MaxAttempts = 1, BaseDelay = TimeSpan.Zero, MaxDelay = TimeSpan.Zero },
            State = new StateSettings { AccessGroup = TestAccessGroup.Name, Path = db },
        };
        var remote = new FakeRemote();
        var source = new FakeSource("scans").Add("a.txt", "a");
        var clean = await new Engine(remote, [source], settings, NullLogger<Engine>.Instance, TimeProvider.System)
            .RunAsync(new RunOptions(), new Progress<RunEvent>(), CancellationToken.None);
        source.Add("b.txt", "b");
        remote.Inject(RemoteOperation.Upload, RemoteResult.Failed("disk full"), pathContains: "b.txt");
        var failing = await new Engine(remote, [source], settings, NullLogger<Engine>.Instance, TimeProvider.System)
            .RunAsync(new RunOptions(), new Progress<RunEvent>(), CancellationToken.None);
        return (db, clean.RunId, failing.RunId);
    }

    [TestMethod]
    public async Task List_runs_prints_one_line_per_run_newest_first_and_honours_limit()
    {
        var (db, clean, failing) = await TwoRuns();

        var all = InvokeWithState(db, "--list-runs");
        var limited = InvokeWithState(db, "--list-runs", "--limit", "1");

        Assert.IsTrue(all.Handled);
        Assert.AreEqual(0, all.ExitCode);
        var lines = all.Out.Split('\n', StringSplitOptions.RemoveEmptyEntries);
        Assert.HasCount(2, lines);
        StringAssert.StartsWith(lines[0], failing.ToString());
        StringAssert.StartsWith(lines[1], clean.ToString());
        Assert.HasCount(1, limited.Out.Split('\n', StringSplitOptions.RemoveEmptyEntries));
    }

    [TestMethod]
    public void List_runs_needs_an_upload_state_and_a_sensible_limit()
    {
        var withoutState = Invoke("--list-runs");
        var badLimit = InvokeWithState("x.db", "--list-runs", "--limit", "abc");

        Assert.AreEqual(2, withoutState.ExitCode);
        StringAssert.Contains(withoutState.Err, "Upload State");
        Assert.AreEqual(2, badLimit.ExitCode);
        StringAssert.Contains(badLimit.Err, "--limit");
    }

    [TestMethod]
    public async Task Export_run_prints_the_report_to_stdout_in_the_chosen_format()
    {
        var (db, _, failing) = await TwoRuns();

        var json = InvokeWithState(db, "--export-run", failing.ToString());
        var csv = InvokeWithState(db, "--export-run", failing.ToString(), "--report-format", "csv");

        Assert.AreEqual(0, json.ExitCode);
        Assert.AreEqual(new RunHistory(new StateSettings { AccessGroup = TestAccessGroup.Name, Path = db }, TimeProvider.System).Export(failing, ReportFormat.Json), json.Out);
        StringAssert.StartsWith(csv.Out, "RunId,StartedAt,");
    }

    [TestMethod]
    public async Task Export_run_with_report_writes_the_file_instead()
    {
        var (db, _, failing) = await TwoRuns();
        var path = Path.Combine(Path.GetDirectoryName(db)!, "out.csv");

        var result = InvokeWithState(db, "--export-run", failing.ToString(), "--report", path, "--report-format", "csv");

        Assert.AreEqual(0, result.ExitCode);
        Assert.AreEqual(path, result.Out.Trim());
        StringAssert.StartsWith(await File.ReadAllTextAsync(path), "RunId,");
    }

    [TestMethod]
    public async Task Export_run_rejects_an_unknown_run_a_bad_id_and_a_bad_format()
    {
        var (db, _, failing) = await TwoRuns();

        Assert.AreEqual(2, InvokeWithState(db, "--export-run", Guid.NewGuid().ToString()).ExitCode);
        Assert.AreEqual(2, InvokeWithState(db, "--export-run", "nonsense").ExitCode);
        Assert.AreEqual(2, InvokeWithState(db, "--export-run", failing.ToString(), "--report-format", "xml").ExitCode);
        Assert.AreEqual(2, InvokeWithState(db, "--export-run").ExitCode);
    }

    [TestMethod]
    public void Help_documents_the_run_history_flags()
    {
        var help = Invoke("--help").Out;

        foreach (var flag in new[] { "--list-runs", "--limit", "--export-run", "--report", "--report-format" })
            StringAssert.Contains(help, flag);
    }

    [TestMethod]
    public void Version_prints_only_the_version()
    {
        var r = Invoke("--version");

        Assert.IsTrue(r.Handled);
        Assert.AreEqual(0, r.ExitCode);
        Assert.AreEqual("1.2.3", r.Out.Trim());
    }

    [TestMethod]
    public void Help_lists_flags_and_the_exit_code_table()
    {
        var r = Invoke("--help");

        Assert.AreEqual(0, r.ExitCode);
        foreach (var expected in new[] { "--headless", "--version", "--help", "130" })
            StringAssert.Contains(r.Out, expected);
    }

    [TestMethod]
    public void Unknown_flag_exits_2_with_a_message_on_stderr()
    {
        var r = Invoke("--bogus");

        Assert.IsTrue(r.Handled);
        Assert.AreEqual(2, r.ExitCode);
        StringAssert.Contains(r.Err, "--bogus");
        Assert.AreEqual("", r.Out);
    }

    [TestMethod]
    public void No_arguments_is_not_handled_so_the_window_opens()
    {
        Assert.IsFalse(Invoke().Handled);
    }

    [TestMethod]
    public void Core_does_not_reference_the_ui_stack()
    {
        var referenced = typeof(Engine).Assembly.GetReferencedAssemblies().Select(a => a.Name!).ToList();

        Assert.IsFalse(referenced.Any(n => n.StartsWith("Avalonia", StringComparison.Ordinal) || n.StartsWith("ReactiveUI", StringComparison.Ordinal)));
    }
}

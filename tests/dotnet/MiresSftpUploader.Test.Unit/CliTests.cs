using MiresSftpUploader.Core;

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
    public void Init_data_dir_creates_the_directory_and_prints_what_it_did()
    {
        if (OperatingSystem.IsWindows()) Assert.Inconclusive("Windows grants BUILTIN\\Users; needs an elevated prompt.");
        var parent = Directory.CreateTempSubdirectory("mires-cli-").FullName;
        var path = Path.Combine(parent, "data");
        var stdout = new StringWriter();
        var stderr = new StringWriter();
        var group = System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo("id", "-gn") { RedirectStandardOutput = true })!
            .StandardOutput.ReadToEnd().Trim();

        var handled = Cli.TryRun(["--init-data-dir", "--data-dir", path], "1.2.3", stdout, stderr, out var exitCode,
            name => name == "State__AccessGroup" ? group : null);

        Assert.IsTrue(handled);
        Assert.AreEqual(0, exitCode, stderr.ToString());
        Assert.IsTrue(Directory.Exists(path));
        StringAssert.Contains(stdout.ToString(), path);
        Directory.Delete(parent, recursive: true);
    }

    [TestMethod]
    public void Init_data_dir_failure_exits_2_with_the_reason_on_stderr()
    {
        if (OperatingSystem.IsWindows()) Assert.Inconclusive("Unix group lookup.");
        var path = Path.Combine(Path.GetTempPath(), "mires-never-created-" + Guid.NewGuid().ToString("N"));
        var r = new StringWriter();
        var stderr = new StringWriter();

        Cli.TryRun(["--init-data-dir", "--data-dir", path], "1.2.3", r, stderr, out var exitCode,
            name => name == "State__AccessGroup" ? "no-such-group-xyz" : null);

        Assert.AreEqual(2, exitCode);
        StringAssert.Contains(stderr.ToString(), "no-such-group-xyz");
        Assert.IsFalse(Directory.Exists(path));
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

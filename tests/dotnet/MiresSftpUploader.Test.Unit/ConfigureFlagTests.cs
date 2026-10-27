using MiresSftpUploader.Core;

namespace MiresSftpUploader.Test.Unit;

/// <summary>--configure starts the Settings TUI: it implies headless, is a mode flag, and honours only --data-dir and --log-level.</summary>
[TestClass]
public sealed class ConfigureFlagTests
{
    [TestMethod]
    public void Configure_is_parsed_and_implies_headless()
    {
        var result = CliOptions.Parse(["--configure"]);

        Assert.IsNull(result.Error);
        Assert.IsTrue(result.Options!.Configure);
        Assert.IsTrue(result.Options.ImpliesHeadless);
    }

    [TestMethod]
    public void Configure_honours_data_dir_and_log_level()
    {
        var result = CliOptions.Parse(["--configure", "--data-dir", "/d", "--log-level=Debug"]);

        Assert.IsNull(result.Error);
        Assert.AreEqual("/d", result.Options!.ConfigOverrides["State:Path"]);
        Assert.AreEqual("Debug", result.Options.ConfigOverrides["Logging:Level"]);
    }

    [TestMethod]
    [DataRow("--headless")]
    [DataRow("--dry-run")]
    [DataRow("--rehash-all")]
    [DataRow("--list-runs")]
    [DataRow("--validate-config")]
    [DataRow("--check-connection")]
    [DataRow("--init-data-dir")]
    [DataRow("--list-secrets")]
    [DataRow("--version")]
    [DataRow("--help")]
    public void Configure_rejects_every_other_switch(string flag)
    {
        Assert.IsNotNull(CliOptions.Parse(["--configure", flag]).Error);
        Assert.IsNotNull(CliOptions.Parse([flag, "--configure"]).Error);
    }

    [TestMethod]
    [DataRow("--source", "a")]
    [DataRow("--report", "r.json")]
    [DataRow("--report-format", "csv")]
    [DataRow("--export-run", "1")]
    [DataRow("--limit", "3")]
    [DataRow("--set-secret", "sftp-password")]
    [DataRow("--clear-secret", "sftp-password")]
    public void Configure_rejects_every_other_value_flag(string flag, string value)
    {
        Assert.IsNotNull(CliOptions.Parse(["--configure", flag, value]).Error);
        Assert.IsNotNull(CliOptions.Parse([flag, value, "--configure"]).Error);
    }

    [TestMethod]
    public void Cli_does_not_handle_configure_so_the_executable_can_start_the_TUI()
    {
        var handled = Cli.TryRun(["--configure"], "1.0", new StringWriter(), new StringWriter(), out _);

        Assert.IsFalse(handled);
    }

    [TestMethod]
    public void A_rejected_combination_exits_2_with_one_stderr_line()
    {
        var err = new StringWriter();

        var handled = Cli.TryRun(["--configure", "--headless"], "1.0", new StringWriter(), err, out var exit);

        Assert.IsTrue(handled);
        Assert.AreEqual(2, exit);
        StringAssert.Contains(err.ToString(), "--configure");
        Assert.AreEqual(1, err.ToString().TrimEnd().Split('\n').Length);
    }

    [TestMethod]
    public void Help_lists_configure()
    {
        StringAssert.Contains(Cli.HelpText, "--configure");
    }
}

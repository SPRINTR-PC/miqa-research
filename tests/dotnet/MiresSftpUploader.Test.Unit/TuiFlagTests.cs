using MiresSftpUploader.Core;

namespace MiresSftpUploader.Test.Unit;

/// <summary>--tui starts the whole-app TUI: a mode flag that implies headless and honours only --data-dir and --log-level.</summary>
[TestClass]
public sealed class TuiFlagTests
{
    [TestMethod]
    public void Tui_is_parsed_and_implies_headless()
    {
        var result = CliOptions.Parse(["--tui"]);

        Assert.IsNull(result.Error);
        Assert.IsTrue(result.Options!.Tui);
        Assert.IsTrue(result.Options.ImpliesHeadless);
    }

    [TestMethod]
    public void Tui_honours_data_dir_and_log_level()
    {
        var result = CliOptions.Parse(["--tui", "--data-dir", "/d", "--log-level=Debug"]);

        Assert.IsNull(result.Error);
        Assert.AreEqual("/d", result.Options!.ConfigOverrides["State:Path"]);
        Assert.AreEqual("Debug", result.Options.ConfigOverrides["Logging:Level"]);
    }

    [TestMethod]
    [DataRow("--configure")]
    [DataRow("--headless")]
    [DataRow("--dry-run")]
    [DataRow("--list-runs")]
    [DataRow("--version")]
    public void Tui_rejects_every_other_switch(string flag)
    {
        Assert.IsNotNull(CliOptions.Parse(["--tui", flag]).Error);
        Assert.IsNotNull(CliOptions.Parse([flag, "--tui"]).Error);
    }

    [TestMethod]
    public void Tui_rejects_value_flags()
    {
        Assert.IsNotNull(CliOptions.Parse(["--tui", "--source", "a"]).Error);
    }

    [TestMethod]
    public void Cli_does_not_handle_tui_so_the_executable_can_start_it()
    {
        Assert.IsFalse(Cli.TryRun(["--tui"], "1.0", new StringWriter(), new StringWriter(), out _));
    }

    [TestMethod]
    public void A_rejected_combination_exits_2_with_one_stderr_line_naming_the_flag()
    {
        var err = new StringWriter();

        Assert.IsTrue(Cli.TryRun(["--tui", "--configure"], "1.0", new StringWriter(), err, out var exit));

        Assert.AreEqual(2, exit);
        StringAssert.Contains(err.ToString(), "--tui");
        Assert.AreEqual(1, err.ToString().TrimEnd().Split('\n').Length);
    }

    [TestMethod]
    public void Help_lists_tui() => StringAssert.Contains(Cli.HelpText, "--tui");

    [TestMethod]
    public void The_Tui_trigger_exists_and_is_recorded_as_text() => Assert.AreEqual("Tui", RunTrigger.Tui.ToString());
}

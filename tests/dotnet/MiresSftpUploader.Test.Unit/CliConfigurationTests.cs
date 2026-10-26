using MiresSftpUploader.Core;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class CliConfigurationTests : ConfigurationTestBase
{
    private (bool Handled, int ExitCode, string Out, string Err) Invoke(string machineJson, params string[] args)
    {
        File.WriteAllText(MachinePath, machineJson);
        var locations = new ConfigurationLocations(MachinePath, UserPath, new Dictionary<string, string?>());
        var stdout = new StringWriter();
        var stderr = new StringWriter();
        var handled = Cli.TryRun(args, "1.2.3", stdout, stderr, out var exitCode, locations);
        return (handled, exitCode, stdout.ToString(), stderr.ToString());
    }

    [TestMethod]
    public void Validate_config_on_a_valid_configuration_exits_0_with_one_line_on_stdout()
    {
        var r = Invoke(ValidMachine().ToJsonString(), "--validate-config");

        Assert.IsTrue(r.Handled);
        Assert.AreEqual(0, r.ExitCode, r.Err);
        Assert.AreEqual(1, r.Out.Trim().Split('\n').Length);
        Assert.AreEqual("", r.Err);
    }

    [TestMethod]
    public void Validate_config_reports_every_error_on_stderr_and_exits_2()
    {
        var r = Invoke("{}", "--validate-config");

        Assert.IsTrue(r.Handled);
        Assert.AreEqual(2, r.ExitCode);
        Assert.AreEqual("", r.Out);
        foreach (var key in new[] { "Sftp:Host", "Sftp:Username", "Sftp:HostKeyFingerprint", "Sources" })
            StringAssert.Contains(r.Err, key);
    }

    [TestMethod]
    public void Validate_config_checks_a_directory_source_as_headless_does()
    {
        var machine = ValidMachine();
        machine["Sources"]![0]!["Path"] = Path.Combine(Dir, "missing");

        var r = Invoke(machine.ToJsonString(), "--validate-config");

        Assert.AreEqual(2, r.ExitCode);
        StringAssert.Contains(r.Err, "Sources:0:Path");
    }

    [TestMethod]
    public void Validate_config_applies_cli_flags_as_the_top_layer()
    {
        var r = Invoke(ValidMachine().ToJsonString(), "--validate-config", "--log-level", "Shouting");

        Assert.AreEqual(2, r.ExitCode);
        StringAssert.Contains(r.Err, "Logging:Level");
    }

    [TestMethod]
    public void A_headless_run_with_an_invalid_configuration_exits_2_with_the_list()
    {
        var r = Invoke("{}", "--headless");

        Assert.IsTrue(r.Handled);
        Assert.AreEqual(2, r.ExitCode);
        StringAssert.Contains(r.Err, "Sftp:Host");
    }

    [TestMethod]
    public void A_headless_run_with_a_valid_configuration_is_left_to_the_caller()
    {
        var r = Invoke(ValidMachine().ToJsonString(), "--headless", "--source", "alpha", "--dry-run");

        Assert.IsFalse(r.Handled);
    }

    [TestMethod]
    public void An_unknown_source_name_exits_2_and_names_the_configured_ones()
    {
        var r = Invoke(ValidMachine().ToJsonString(), "--headless", "--source", "alpha", "--source", "nope");

        Assert.IsTrue(r.Handled);
        Assert.AreEqual(2, r.ExitCode);
        StringAssert.Contains(r.Err, "nope");
        StringAssert.Contains(r.Err, "alpha");
    }

    [TestMethod]
    public void Source_names_match_case_insensitively()
    {
        Assert.IsFalse(Invoke(ValidMachine().ToJsonString(), "--headless", "--source=ALPHA").Handled);
    }

    [TestMethod]
    public void A_flag_missing_its_value_exits_2()
    {
        var r = Invoke(ValidMachine().ToJsonString(), "--headless", "--source");

        Assert.AreEqual(2, r.ExitCode);
        StringAssert.Contains(r.Err, "--source");
    }

    [TestMethod]
    public void Help_lists_every_documented_flag_and_no_config_file_flag()
    {
        foreach (var flag in new[] { "--headless", "--source", "--dry-run", "--rehash-all", "--report", "--report-format", "--export-run", "--list-runs", "--limit", "--validate-config", "--check-connection", "--init-data-dir", "--log-level", "--data-dir", "--version", "--help" })
            StringAssert.Contains(Cli.HelpText, flag);
        Assert.IsFalse(Cli.HelpText.Contains("--config "));
    }

    [TestMethod]
    public void Parse_maps_flags_to_options_and_config_overrides()
    {
        var parsed = CliOptions.Parse(["--source", "a", "--source", "b", "--dry-run", "--rehash-all", "--report-format", "csv", "--log-level", "Debug", "--list-runs", "--limit", "5"]);

        var o = parsed.Options!;
        CollectionAssert.AreEqual(new[] { "a", "b" }, o.Sources.ToArray());
        Assert.IsTrue(o.DryRun);
        Assert.IsTrue(o.ListRuns);
        Assert.IsTrue(o.ImpliesHeadless);
        Assert.AreEqual(5, o.Limit);
        Assert.AreEqual("true", o.ConfigOverrides["Upload:RehashAll"]);
        Assert.AreEqual("csv", o.ConfigOverrides["Report:Format"]);
        Assert.AreEqual("Debug", o.ConfigOverrides["Logging:Level"]);
        Assert.IsFalse(CliOptions.Parse([]).Options!.ImpliesHeadless);
    }
}

using System.Diagnostics;
using System.Text.Json.Nodes;
using MiresSftpUploader.Core;

namespace MiresSftpUploader.Test.Unit;

/// <summary>--init-data-dir and how the Data Directory and its access group are layered from configuration.</summary>
[TestClass]
public sealed class DataDirectoryCliTests : ConfigurationTestBase
{
    private ConfigurationLocations Locations(JsonObject? machine = null, JsonObject? user = null, params (string Name, string Value)[] env)
    {
        File.WriteAllText(MachinePath, (machine ?? new JsonObject()).ToJsonString());
        if (user is not null) File.WriteAllText(UserPath, user.ToJsonString());
        return new ConfigurationLocations(MachinePath, UserPath, env.ToDictionary(e => e.Name, e => (string?)e.Value));
    }

    private static string MyGroup()
    {
        var start = new ProcessStartInfo("id", "-gn") { RedirectStandardOutput = true, UseShellExecute = false };
        using var process = Process.Start(start)!;
        var group = process.StandardOutput.ReadToEnd().Trim();
        process.WaitForExit();
        return group;
    }

    private static JsonObject StateWith(string key, string value) => new() { ["State"] = new JsonObject { [key] = value } };

    [TestMethod]
    public void Data_dir_flag_beats_MIRES_DATA_DIR_beats_Machine_Config()
    {
        var machine = StateWith("Path", "/machine");

        Assert.AreEqual("/machine", new Configuration(Locations(machine)).ResolveDataDirectory().Path);
        Assert.AreEqual("/env", new Configuration(Locations(machine, null, ("MIRES_DATA_DIR", "/env"))).ResolveDataDirectory().Path);

        var cli = CliOptions.Parse(["--data-dir", "/flag"]).Options;
        Assert.AreEqual("/flag", new Configuration(Locations(machine, null, ("MIRES_DATA_DIR", "/env"))).ResolveDataDirectory(cli).Path);
    }

    [TestMethod]
    public void Without_any_setting_the_per_OS_default_is_used()
    {
        var path = new Configuration(Locations()).ResolveDataDirectory().Path;

        Assert.IsTrue(path.EndsWith("MiresSftpUploader", StringComparison.Ordinal) || path == "/var/lib/mires-sftp-uploader", path);
    }

    [TestMethod]
    public void Access_group_comes_from_Machine_Config_or_the_environment_never_from_User_Overrides()
    {
        Assert.AreEqual("lab", new Configuration(Locations(StateWith("AccessGroup", "lab"))).ResolveDataDirectory().AccessGroup);
        Assert.AreEqual("envgrp", new Configuration(Locations(StateWith("AccessGroup", "lab"), null, ("MIRES_State__AccessGroup", "envgrp"))).ResolveDataDirectory().AccessGroup);
        Assert.IsNull(new Configuration(Locations(null, StateWith("AccessGroup", "sneaky"))).ResolveDataDirectory().AccessGroup);
    }

    [TestMethod]
    public void Access_group_cannot_be_saved_from_the_UI()
    {
        var configuration = new Configuration(Locations());

        var saved = configuration.Save(new Dictionary<string, string?> { ["State:AccessGroup"] = "sneaky" });

        Assert.IsFalse(saved.Succeeded);
        Assert.IsFalse(File.Exists(UserPath));
    }

    [TestMethod]
    public void Init_data_dir_sets_up_the_directory_and_reports_what_it_did()
    {
        if (OperatingSystem.IsWindows()) Assert.Inconclusive("Windows grants BUILTIN\\Users; needs an elevated prompt.");
        var stdout = new StringWriter();
        var stderr = new StringWriter();
        var locations = Locations(StateWith("AccessGroup", MyGroup()));

        var handled = Cli.TryRun(["--init-data-dir", "--data-dir", DataDir], "1.2.3", stdout, stderr, out var exitCode, locations);

        Assert.IsTrue(handled);
        Assert.AreEqual(0, exitCode, stderr.ToString());
        Assert.IsTrue(Directory.Exists(DataDir));
        StringAssert.Contains(stdout.ToString(), DataDir);
    }

    [TestMethod]
    public void Init_data_dir_with_a_missing_group_exits_2_and_names_it()
    {
        if (OperatingSystem.IsWindows()) Assert.Inconclusive("Unix group lookup.");
        var stderr = new StringWriter();
        var locations = Locations(null, null, ("MIRES_State__AccessGroup", "no-such-group-xyz"));

        Cli.TryRun(["--init-data-dir", "--data-dir", DataDir], "1.2.3", new StringWriter(), stderr, out var exitCode, locations);

        Assert.AreEqual(2, exitCode);
        StringAssert.Contains(stderr.ToString(), "no-such-group-xyz");
        Assert.IsFalse(Directory.Exists(DataDir));
    }

    [TestMethod]
    public void Init_data_dir_does_not_need_the_rest_of_the_configuration_to_be_valid()
    {
        if (OperatingSystem.IsWindows()) Assert.Inconclusive("Unix group lookup.");
        var locations = Locations(StateWith("AccessGroup", MyGroup()));

        Cli.TryRun(["--init-data-dir", "--data-dir", DataDir], "1.2.3", new StringWriter(), new StringWriter(), out var exitCode, locations);

        Assert.AreEqual(0, exitCode, "the machine config has no Sftp or Sources section");
    }

    [TestMethod]
    public void Init_data_dir_works_before_any_Machine_Config_exists()
    {
        var locations = new ConfigurationLocations(MachinePath, UserPath, new Dictionary<string, string?> { ["MIRES_State__AccessGroup"] = "no-such-group-xyz" });
        var stderr = new StringWriter();

        Cli.TryRun(["--init-data-dir", "--data-dir", DataDir], "1.2.3", new StringWriter(), stderr, out var exitCode, locations);

        Assert.AreEqual(2, exitCode);
        StringAssert.Contains(stderr.ToString(), "no-such-group-xyz");
        Assert.DoesNotContain("Machine Config not found", stderr.ToString());
    }
}

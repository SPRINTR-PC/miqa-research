using System.Text.Json.Nodes;
using MiresSftpUploader.Core;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class ConfigurationSaveTests : ConfigurationTestBase
{
    private JsonObject SavedUserFile() => JsonNode.Parse(File.ReadAllText(UserPath))!.AsObject();

    [TestMethod]
    public void Save_writes_only_the_changed_keys_with_the_config_version_and_load_sees_them()
    {
        var cfg = Create(ValidMachine().ToJsonString());

        var saved = cfg.Save(new Dictionary<string, string?> { ["Upload:MaxParallelUploads"] = "5", ["Ui:Theme"] = "Light" });

        Assert.IsTrue(saved.Succeeded, string.Join(" | ", saved.Errors));
        var file = SavedUserFile();
        Assert.AreEqual(1, (int)file["ConfigVersion"]!);
        Assert.AreEqual(5, (int)file["Upload"]!["MaxParallelUploads"]!);
        Assert.AreEqual("Light", (string)file["Ui"]!["Theme"]!);
        CollectionAssert.AreEquivalent(new[] { "ConfigVersion", "Upload", "Ui" }, file.Select(p => p.Key).ToArray());
        var r = cfg.Load();
        Assert.AreEqual(5, r.Config!.Upload.MaxParallelUploads);
        Assert.AreEqual(UiTheme.Light, r.Config.Ui.Theme);
        Assert.AreEqual(ConfigLayer.User, r.Setting("Ui:Theme").Layer);
    }

    [TestMethod]
    public void A_value_equal_to_the_current_one_is_not_written()
    {
        var cfg = Create(ValidMachine().ToJsonString());

        var saved = cfg.Save(new Dictionary<string, string?> { ["Sftp:Port"] = "22", ["Sftp:Username"] = "u" });

        Assert.IsTrue(saved.Succeeded);
        Assert.IsFalse(File.Exists(UserPath), "nothing changed, so nothing is written");
    }

    [TestMethod]
    public void Save_keeps_earlier_overrides_and_null_removes_one()
    {
        var cfg = Create(ValidMachine().ToJsonString(), """{ "ConfigVersion": 1, "Ui": { "Theme": "Light" }, "Retry": { "MaxAttempts": 4 } }""");

        var saved = cfg.Save(new Dictionary<string, string?> { ["Ui:Theme"] = null, ["Upload:MaxParallelUploads"] = "2" });

        Assert.IsTrue(saved.Succeeded, string.Join(" | ", saved.Errors));
        var r = cfg.Load();
        Assert.AreEqual(UiTheme.Dark, r.Config!.Ui.Theme);
        Assert.AreEqual(4, r.Config.Retry.MaxAttempts);
        Assert.AreEqual(2, r.Config.Upload.MaxParallelUploads);
    }

    [TestMethod]
    public void An_invalid_change_reports_the_errors_and_leaves_the_file_untouched()
    {
        const string original = """{ "ConfigVersion": 1, "Ui": { "Theme": "Light" } }""";
        var cfg = Create(ValidMachine().ToJsonString(), original);

        var saved = cfg.Save(new Dictionary<string, string?> { ["Upload:MaxParallelUploads"] = "99", ["Ignore:Patterns:0"] = "([" });

        Assert.IsFalse(saved.Succeeded);
        Assert.IsTrue(saved.Errors.Any(e => e.Key == "Upload:MaxParallelUploads"));
        Assert.IsTrue(saved.Errors.Any(e => e.Key == "Ignore:Patterns:0"));
        Assert.AreEqual(original, File.ReadAllText(UserPath));
    }

    [TestMethod]
    public void Locked_settings_cannot_be_saved()
    {
        var cfg = Create(ValidMachine().ToJsonString(), env: new() { ["MIRES_Sftp__Port"] = "2200" });

        var saved = cfg.Save(new Dictionary<string, string?> { ["Sftp:Port"] = "2300" });

        Assert.IsFalse(saved.Succeeded);
        Assert.IsTrue(saved.Errors.Any(e => e.Key == "Sftp:Port" && e.Message.Contains("locked", StringComparison.OrdinalIgnoreCase)));
        Assert.IsFalse(File.Exists(UserPath));
    }

    [TestMethod]
    public void Settings_of_a_read_only_machine_config_cannot_be_saved()
    {
        if (OperatingSystem.IsWindows() || Environment.UserName == "root") Assert.Inconclusive("Needs Unix permissions and a non-root user.");
        var cfg = Create(ValidMachine().ToJsonString());
        File.SetUnixFileMode(Path.Combine(Dir, "install"), UnixFileMode.UserRead | UnixFileMode.UserExecute);

        var saved = cfg.Save(new Dictionary<string, string?> { ["Sftp:Host"] = "other.example.org" });

        Assert.IsFalse(saved.Succeeded);
        Assert.IsFalse(File.Exists(UserPath));
    }

    [TestMethod]
    public void Secrets_cannot_be_saved()
    {
        var cfg = Create(ValidMachine().ToJsonString());

        var saved = cfg.Save(new Dictionary<string, string?> { ["Sftp:Password"] = "hunter2" });

        Assert.IsFalse(saved.Succeeded);
        Assert.IsFalse(File.Exists(UserPath));
    }

    [TestMethod]
    public void Changing_one_array_element_saves_the_whole_array()
    {
        var machine = ValidMachine();
        machine["Sources"] = new JsonArray(
            new JsonObject { ["Name"] = "a", ["Path"] = DataDir },
            new JsonObject { ["Name"] = "b", ["Path"] = DataDir });
        var cfg = Create(machine.ToJsonString());

        var saved = cfg.Save(new Dictionary<string, string?> { ["Sources:1:Name"] = "renamed" });

        Assert.IsTrue(saved.Succeeded, string.Join(" | ", saved.Errors));
        Assert.AreEqual(2, SavedUserFile()["Sources"]!.AsArray().Count);
        CollectionAssert.AreEqual(new[] { "a", "renamed" }, cfg.Load().Config!.Sources.Select(s => s.Name).ToArray());
    }

    [TestMethod]
    public void An_empty_array_token_clears_a_list_from_lower_layers()
    {
        var machine = ValidMachine();
        machine["Ignore"] = new JsonObject { ["Files"] = new JsonArray("x", "y") };
        var cfg = Create(machine.ToJsonString());

        var saved = cfg.Save(new Dictionary<string, string?> { ["Ignore:Files"] = "[]" });

        Assert.IsTrue(saved.Succeeded, string.Join(" | ", saved.Errors));
        Assert.AreEqual(0, cfg.Load().Config!.Ignore.Files.Count);
    }

    [TestMethod]
    public void Save_leaves_no_temporary_files_behind()
    {
        var cfg = Create(ValidMachine().ToJsonString());

        cfg.Save(new Dictionary<string, string?> { ["Ui:Theme"] = "System" });
        cfg.Save(new Dictionary<string, string?> { ["Ui:Theme"] = "Light" });

        CollectionAssert.AreEqual(new[] { "appsettings.user.json" }, Directory.GetFiles(Path.Combine(Dir, "user")).Select(Path.GetFileName).ToArray());
    }

    [TestMethod]
    public void A_user_file_from_a_newer_version_is_an_error()
    {
        var cfg = Create(ValidMachine().ToJsonString(), """{ "ConfigVersion": 2 }""");

        var r = cfg.Load();

        Assert.IsFalse(r.Succeeded);
        Assert.IsTrue(r.Errors.Any(e => e.Key == "ConfigVersion"));
    }
}

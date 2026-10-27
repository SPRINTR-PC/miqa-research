using System.Text.Json.Nodes;
using MiresSftpUploader.Core;

namespace MiresSftpUploader.Test.Unit;

/// <summary>Shared fixture: a temp install folder (Machine Config) and a temp per-user folder (User Overrides).</summary>
public abstract class ConfigurationTestBase
{
    protected string Dir = "";

    [TestInitialize]
    public void Setup()
    {
        Dir = Path.Combine(Path.GetTempPath(), "mires-cfg-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(Path.Combine(Dir, "install"));
        Directory.CreateDirectory(Path.Combine(Dir, "user"));
    }

    [TestCleanup]
    public void Cleanup()
    {
        try
        {
            if (!OperatingSystem.IsWindows())
                File.SetUnixFileMode(Path.Combine(Dir, "install"), UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute);
            Directory.Delete(Dir, true);
        }
        catch (IOException) { }
    }

    protected string MachinePath => Path.Combine(Dir, "install", "appsettings.json");
    protected string UserPath => Path.Combine(Dir, "user", "appsettings.user.json");

    protected string DataDir => Path.Combine(Dir, "data");

    /// <summary>A valid configuration; each test changes one thing in it.</summary>
    protected JsonObject ValidMachine()
    {
        Directory.CreateDirectory(DataDir);
        return JsonNode.Parse($$"""
            {
              "Sftp": { "Host": "sftp.example.org", "Username": "u", "HostKeyFingerprint": "abc", "RemoteRoot": "/incoming" },
              "Sources": [ { "Name": "alpha", "Type": "Directory", "Path": {{System.Text.Json.JsonSerializer.Serialize(DataDir)}} } ]
            }
            """)!.AsObject();
    }

    protected Configuration Create(string machineJson, string? userJson = null, Dictionary<string, string?>? env = null)
    {
        File.WriteAllText(MachinePath, machineJson);
        if (userJson is not null) File.WriteAllText(UserPath, userJson);
        return new Configuration(new ConfigurationLocations(MachinePath, UserPath, env ?? []));
    }
}

[TestClass]
public sealed class ConfigurationLayeringTests : ConfigurationTestBase
{
    [TestMethod]
    public void Machine_config_values_are_loaded_and_unset_keys_take_documented_defaults()
    {
        var machine = ValidMachine();
        machine["Sftp"]!["Host"] = "sftp.example.org";
        machine["Sftp"]!["Port"] = 2222;
        var cfg = Create(machine.ToJsonString());

        var r = cfg.Load();

        Assert.IsTrue(r.Succeeded, string.Join(" | ", r.Errors));

        Assert.IsNotNull(r.Config);
        Assert.AreEqual("sftp.example.org", r.Config.Sftp.Host);
        Assert.AreEqual(2222, r.Config.Sftp.Port);
        Assert.AreEqual(3, r.Config.Upload.MaxParallelUploads);
        Assert.AreEqual(UiTheme.Dark, r.Config.Ui.Theme);
    }

    [TestMethod]
    public void Layers_override_in_order_machine_user_environment_cli()
    {
        var machine = ValidMachine();
        machine["Sftp"] = new JsonObject { ["Host"] = "machine", ["Username"] = "machine", ["HostKeyFingerprint"] = "fp", ["RemoteRoot"] = "/machine" };
        machine["Scan"] = new JsonObject { ["MinFileAgeSeconds"] = 10 };
        machine["Upload"] = new JsonObject { ["MaxParallelUploads"] = 2 };
        var cfg = Create(
            machine.ToJsonString(),
            """{ "ConfigVersion": 1, "Scan": { "MinFileAgeSeconds": 20 }, "Upload": { "MaxParallelUploads": 4 } }""",
            new() { ["MIRES_Sftp__Host"] = "env", ["MIRES_Upload__MaxParallelUploads"] = "6" });
        var cli = CliOptions.Parse(["--data-dir", "/cli/data"]).Options!;

        var r = cfg.Load(cli);

        Assert.AreEqual("env", r.Config!.Sftp.Host);
        Assert.AreEqual("machine", r.Config.Sftp.Username);
        Assert.AreEqual("/machine", r.Config.Sftp.RemoteRoot);
        Assert.AreEqual(20, r.Config.Scan.MinFileAgeSeconds);
        Assert.AreEqual(6, r.Config.Upload.MaxParallelUploads);
        Assert.AreEqual("/cli/data", r.Config.State.Path);
        Assert.AreEqual(ConfigLayer.Environment, r.Setting("Sftp:Host").Layer);
        Assert.AreEqual(ConfigLayer.Machine, r.Setting("Sftp:Username").Layer);
        Assert.AreEqual(ConfigLayer.User, r.Setting("Scan:MinFileAgeSeconds").Layer);
        Assert.AreEqual(ConfigLayer.Environment, r.Setting("Upload:MaxParallelUploads").Layer);
        Assert.AreEqual(ConfigLayer.Cli, r.Setting("State:Path").Layer);
        Assert.AreEqual(ConfigLayer.Default, r.Setting("Sftp:Port").Layer);
    }

    [TestMethod]
    public void Sources_and_Sftp_settings_in_User_Overrides_are_ignored_with_a_warning()
    {
        var machine = ValidMachine();
        machine["Sftp"] = new JsonObject { ["Host"] = "machine", ["Username"] = "machine", ["HostKeyFingerprint"] = "fp", ["RemoteRoot"] = "/machine" };
        var cfg = Create(machine.ToJsonString(),
            $$"""{ "Sftp": { "Username": "user" }, "Sources": [ { "Name": "mine", "Type": "Directory", "Path": {{System.Text.Json.JsonSerializer.Serialize(DataDir)}} } ] }""");

        var r = cfg.Load();

        Assert.AreEqual("machine", r.Config!.Sftp.Username);
        CollectionAssert.AreEqual(new[] { "alpha" }, r.Config.Sources.Select(x => x.Name).ToArray());
        Assert.IsTrue(r.Warnings.Any(w => w.Key == "Sftp:Username" && w.Message.Contains("ignored in User Overrides")));
        Assert.IsTrue(r.Warnings.Any(w => w.Key == "Sources" && w.Message.Contains("ignored in User Overrides")));
    }

    [TestMethod]
    public void An_array_is_replaced_whole_by_the_highest_layer_that_defines_it()
    {
        var machine = ValidMachine();
        machine["Sources"] = new JsonArray(
            new JsonObject { ["Name"] = "a", ["Path"] = DataDir },
            new JsonObject { ["Name"] = "b", ["Path"] = DataDir });
        machine["Ignore"] = new JsonObject { ["Files"] = new JsonArray("x", "y") };
        var cfg = Create(
            machine.ToJsonString(),
            """{ "Ignore": { "Files": ["z"] } }""",
            new() { ["MIRES_Sources__0__Name"] = "only", ["MIRES_Sources__0__Path"] = DataDir });

        var r = cfg.Load();

        CollectionAssert.AreEqual(new[] { "only" }, r.Config!.Sources.Select(s => s.Name).ToArray());
        Assert.AreEqual(DataDir, r.Config.Sources[0].Path);
        CollectionAssert.AreEqual(new[] { "z" }, r.Config.Ignore.Files.ToArray());
    }

    [TestMethod]
    public void Environment_supplied_keys_are_locked_and_other_keys_are_writable()
    {
        var cfg = Create(ValidMachine().ToJsonString(), env: new() { ["MIRES_Sftp__Port"] = "2200" });

        var r = cfg.Load();

        Assert.IsTrue(r.Setting("Sftp:Port").Locked);
        Assert.IsFalse(r.Setting("Sftp:Username").Locked);
    }

    [TestMethod]
    public void Machine_config_in_a_read_only_folder_makes_its_keys_locked()
    {
        if (OperatingSystem.IsWindows()) Assert.Inconclusive("Uses Unix permissions.");
        var cfg = Create(ValidMachine().ToJsonString());
        File.SetUnixFileMode(Path.Combine(Dir, "install"), UnixFileMode.UserRead | UnixFileMode.UserExecute);
        if (Environment.UserName == "root") Assert.Inconclusive("root ignores permissions.");

        var r = cfg.Load();

        Assert.IsTrue(r.Setting("Sftp:Host").Locked);
        Assert.IsTrue(r.Setting("Sftp:Port").Locked, "an unset Sftp key is kept in Machine Config too, so it cannot be changed");
        Assert.IsTrue(r.Setting("Sources").Locked);
        Assert.IsFalse(r.Setting("Upload:MaxParallelUploads").Locked, "other keys fall to the default and are editable in User Overrides");
    }

    [TestMethod]
    public void Missing_machine_config_is_an_error()
    {
        var cfg = new Configuration(new ConfigurationLocations(MachinePath, UserPath, new Dictionary<string, string?>()));

        var r = cfg.Load();

        Assert.IsNull(r.Config);
        Assert.AreEqual(1, r.Errors.Count);
        StringAssert.Contains(r.Errors[0].Message, "appsettings.json");
    }
}

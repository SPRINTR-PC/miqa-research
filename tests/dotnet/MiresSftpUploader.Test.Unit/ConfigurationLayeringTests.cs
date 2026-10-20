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
        var cfg = Create("""{ "Sftp": { "Host": "sftp.example.org", "Port": 2222 } }""");

        var r = cfg.Load();

        Assert.IsNotNull(r.Config);
        Assert.AreEqual("sftp.example.org", r.Config.Sftp.Host);
        Assert.AreEqual(2222, r.Config.Sftp.Port);
        Assert.AreEqual(3, r.Config.Upload.MaxParallelUploads);
        Assert.AreEqual(UiTheme.Dark, r.Config.Ui.Theme);
    }

    [TestMethod]
    public void Layers_override_in_order_machine_user_environment_cli()
    {
        var cfg = Create(
            """{ "Sftp": { "Host": "machine", "Username": "machine" , "RemoteRoot": "/machine" } }""",
            """{ "ConfigVersion": 1, "Sftp": { "Host": "user", "Username": "user" } }""",
            new() { ["MIRES_Sftp__Host"] = "env" });
        var cli = CliOptions.Parse(["--data-dir", "/cli/data"]).Options!;

        var r = cfg.Load(cli);

        Assert.AreEqual("env", r.Config!.Sftp.Host);
        Assert.AreEqual("user", r.Config.Sftp.Username);
        Assert.AreEqual("/machine", r.Config.Sftp.RemoteRoot);
        Assert.AreEqual("/cli/data", r.Config.State.Path);
        Assert.AreEqual(ConfigLayer.Environment, r.Setting("Sftp:Host").Layer);
        Assert.AreEqual(ConfigLayer.User, r.Setting("Sftp:Username").Layer);
        Assert.AreEqual(ConfigLayer.Machine, r.Setting("Sftp:RemoteRoot").Layer);
        Assert.AreEqual(ConfigLayer.Cli, r.Setting("State:Path").Layer);
        Assert.AreEqual(ConfigLayer.Default, r.Setting("Sftp:Port").Layer);
    }

    [TestMethod]
    public void An_array_is_replaced_whole_by_the_highest_layer_that_defines_it()
    {
        var cfg = Create(
            """{ "Sources": [ { "Name": "a", "Path": "/a" }, { "Name": "b", "Path": "/b" } ], "Ignore": { "Files": ["x", "y"] } }""",
            """{ "Ignore": { "Files": ["z"] } }""",
            new() { ["MIRES_Sources__0__Name"] = "only" });

        var r = cfg.Load();

        CollectionAssert.AreEqual(new[] { "only" }, r.Config!.Sources.Select(s => s.Name).ToArray());
        Assert.IsNull(r.Config.Sources[0].Path);
        CollectionAssert.AreEqual(new[] { "z" }, r.Config.Ignore.Files.ToArray());
    }

    [TestMethod]
    public void Environment_supplied_keys_are_locked_and_other_keys_are_writable()
    {
        var cfg = Create("""{ "Sftp": { "Host": "h" } }""", env: new() { ["MIRES_Sftp__Port"] = "2200" });

        var r = cfg.Load();

        Assert.IsTrue(r.Setting("Sftp:Port").Locked);
        Assert.IsFalse(r.Setting("Sftp:Username").Locked);
    }

    [TestMethod]
    public void Machine_config_in_a_read_only_folder_makes_its_keys_locked()
    {
        if (OperatingSystem.IsWindows()) Assert.Inconclusive("Uses Unix permissions.");
        var cfg = Create("""{ "Sftp": { "Host": "h" } }""", """{ "Sftp": { "Username": "u" } }""");
        File.SetUnixFileMode(Path.Combine(Dir, "install"), UnixFileMode.UserRead | UnixFileMode.UserExecute);
        if (Environment.UserName == "root") Assert.Inconclusive("root ignores permissions.");

        var r = cfg.Load();

        Assert.IsTrue(r.Setting("Sftp:Host").Locked);
        Assert.IsFalse(r.Setting("Sftp:Username").Locked, "a key the user already overrides stays editable");
        Assert.IsFalse(r.Setting("Sftp:Port").Locked, "an unset key falls to the default and is editable");
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

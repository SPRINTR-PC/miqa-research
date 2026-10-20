using System.Reactive.Linq;
using System.Reactive.Threading.Tasks;
using System.Linq;
using MiresSftpUploader.Core;
using MiresSftpUploader.ViewModels;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class SettingsPageViewModelTests : ConfigurationTestBase
{
    private static SettingsPageViewModel NewPage(Configuration cfg, Func<string, DataDirectoryAccess>? check = null, Func<string, long>? freeSpace = null) =>
        new(cfg, check ?? (path => Access(path)), freeSpace ?? (_ => long.MaxValue));

    private static DataDirectoryAccess Access(string path, bool writable = true) =>
        new(path, true, writable, "alice", "mires-uploader", 4096, 10L * 1024 * 1024 * 1024, false, $"sudo mires --init-data-dir --data-dir {path}",
            writable ? null : $"The Data Directory '{path}' is not writable by account 'alice'.");

    private static bool CanSave(SettingsPageViewModel page) => page.SaveCommand.CanExecute.FirstAsync().ToTask().Result;

    private static void Save(SettingsPageViewModel page) => page.SaveCommand.Execute().Subscribe();

    [TestMethod]
    public void Fields_show_the_effective_values_and_the_Sources()
    {
        var cfg = Create(ValidMachine().ToJsonString());

        var page = NewPage(cfg);

        Assert.AreEqual("sftp.example.org", page.Field("Sftp:Host").Value);
        Assert.AreEqual("22", page.Field("Sftp:Port").Value, "a default is shown too");
        Assert.HasCount(1, page.Sources);
        Assert.AreEqual("alpha", page.Sources[0].Name);
        Assert.IsTrue(page.Sources[0].IsDirectory);
        Assert.AreEqual(DataDir, page.Sources[0].Path);
    }

    [TestMethod]
    public void A_setting_from_the_environment_is_locked_and_says_why()
    {
        var cfg = Create(ValidMachine().ToJsonString(), env: new() { ["MIRES_Sftp__Host"] = "env.example.org" });

        var page = NewPage(cfg);

        var host = page.Field("Sftp:Host");
        Assert.AreEqual("env.example.org", host.Value);
        Assert.IsTrue(host.IsLocked);
        Assert.IsFalse(host.IsEditable);
        StringAssert.Contains(host.LockReason, "environment");
        Assert.IsFalse(page.Field("Sftp:Username").IsLocked);
    }

    [TestMethod]
    public void A_read_only_Machine_Config_locks_the_settings_it_defines()
    {
        var cfg = Create(ValidMachine().ToJsonString());
        if (OperatingSystem.IsWindows()) Assert.Inconclusive("needs POSIX permissions");
        File.SetUnixFileMode(Path.Combine(Dir, "install"), UnixFileMode.UserRead | UnixFileMode.UserExecute);

        var page = NewPage(cfg);

        Assert.IsTrue(page.Field("Sftp:Host").IsLocked);
        StringAssert.Contains(page.Field("Sftp:Host").LockReason, "Machine Config");
        Assert.IsTrue(page.SourcesLocked);
        Assert.IsFalse(page.Field("Upload:MaxParallelUploads").IsLocked, "a default is editable: it goes to User Overrides");
    }

    [TestMethod]
    public void A_validation_error_shows_inline_and_disables_Save_until_fixed()
    {
        var page = NewPage(Create(ValidMachine().ToJsonString()));

        page.Field("Sftp:Port").Value = "0";

        StringAssert.Contains(page.Field("Sftp:Port").Error, "out of range");
        Assert.IsTrue(page.HasErrors);
        Assert.IsFalse(CanSave(page));

        page.Field("Sftp:Port").Value = "2222";

        Assert.IsNull(page.Field("Sftp:Port").Error);
        Assert.IsTrue(CanSave(page));
    }

    [TestMethod]
    public void Text_that_is_not_a_number_is_an_inline_error()
    {
        var page = NewPage(Create(ValidMachine().ToJsonString()));

        page.Field("Sftp:Port").Value = "twenty";

        StringAssert.Contains(page.Field("Sftp:Port").Error, "whole number");
        Assert.IsFalse(CanSave(page));
    }

    [TestMethod]
    public void Save_writes_the_changes_to_User_Overrides()
    {
        var cfg = Create(ValidMachine().ToJsonString());
        var page = NewPage(cfg);
        Assert.IsFalse(CanSave(page), "nothing changed");

        page.Field("Upload:MaxParallelUploads").Value = "5";
        page.Field("Ui:Theme").Value = "Light";
        Save(page);

        Assert.AreEqual(5, cfg.Load().Config!.Upload.MaxParallelUploads);
        Assert.AreEqual(UiTheme.Light, cfg.Load().Config!.Ui.Theme);
        Assert.IsFalse(page.HasChanges);
        Assert.IsFalse(CanSave(page));
    }

    [TestMethod]
    public void Clearing_a_field_removes_its_User_Override()
    {
        var cfg = Create(ValidMachine().ToJsonString(), """{ "ConfigVersion": 1, "Logging": { "Directory": "/var/log/x" } }""");
        var page = NewPage(cfg);
        Assert.AreEqual("/var/log/x", page.Field("Logging:Directory").Value);

        page.Field("Logging:Directory").Value = "";
        Save(page);

        Assert.IsNull(cfg.Load().Config!.Logging.Directory);
    }

    [TestMethod]
    public void Upload_VerifyCommand_and_State_AccessGroup_are_not_editable_in_the_UI()
    {
        var page = NewPage(Create(ValidMachine().ToJsonString()));

        Assert.IsFalse(page.TryGetField("Upload:VerifyCommand", out _));
        Assert.IsFalse(page.TryGetField("State:AccessGroup", out _));
    }

    [TestMethod]
    public void The_Logging_directory_and_State_Path_are_editable()
    {
        var cfg = Create(ValidMachine().ToJsonString());
        var page = NewPage(cfg);
        var logs = Path.Combine(Dir, "logs");

        page.Field("Logging:Directory").Value = logs;
        Save(page);

        Assert.AreEqual(logs, cfg.Load().Config!.Logging.Directory);
        Assert.IsTrue(page.Field("State:Path").IsEditable);
    }

    // ---- Sources ----

    [TestMethod]
    public void Adding_an_S3_Source_saves_it_with_its_own_fields_and_no_Directory_path()
    {
        var cfg = Create(ValidMachine().ToJsonString());
        var page = NewPage(cfg);

        page.AddSourceCommand.Execute().Subscribe();
        var added = page.Sources[1];
        Assert.IsTrue(added.IsDirectory, "a new Source starts as a Directory");
        added.TypeName = "S3";
        Assert.IsTrue(added.IsS3);
        Assert.IsFalse(added.IsDirectory);
        added.Name = "wsi-bucket";
        added.Endpoint = "https://s3.example.org";
        added.Bucket = "slides";
        added.Prefix = "in/";
        added.Region = "eu-north-1";
        added.ForcePathStyle = true;
        added.RemotePath = "/incoming/wsi";
        Save(page);

        var saved = cfg.Load().Config!.Sources;
        CollectionAssert.AreEqual(new[] { "alpha", "wsi-bucket" }, saved.Select(x => x.Name).ToArray());
        var s3 = saved[1];
        Assert.AreEqual(SourceType.S3, s3.Type);
        Assert.AreEqual("https://s3.example.org", s3.Endpoint);
        Assert.AreEqual("slides", s3.Bucket);
        Assert.AreEqual("in/", s3.Prefix);
        Assert.AreEqual("eu-north-1", s3.Region);
        Assert.IsTrue(s3.ForcePathStyle);
        Assert.AreEqual("/incoming/wsi", s3.RemotePath);
        Assert.IsNull(s3.Path);
        Assert.AreEqual(DataDir, saved[0].Path, "the existing Source is unchanged");
    }

    [TestMethod]
    public void Removing_a_Source_saves_the_remaining_ones()
    {
        var machine = ValidMachine();
        machine["Sources"]!.AsArray().Add(System.Text.Json.Nodes.JsonNode.Parse($$"""{ "Name": "beta", "Type": "Directory", "Path": {{System.Text.Json.JsonSerializer.Serialize(DataDir)}} }"""));
        var cfg = Create(machine.ToJsonString());
        var page = NewPage(cfg);
        Assert.HasCount(2, page.Sources);

        page.RemoveSourceCommand.Execute(page.Sources[0]).Subscribe();
        Save(page);

        CollectionAssert.AreEqual(new[] { "beta" }, cfg.Load().Config!.Sources.Select(x => x.Name).ToArray());
    }

    [TestMethod]
    public void Editing_a_Source_keeps_the_settings_the_page_does_not_edit()
    {
        var machine = ValidMachine();
        machine["Sources"]![0]!["Ignore"] = System.Text.Json.Nodes.JsonNode.Parse("""{ "Files": ["skip.txt"] }""");
        machine["Sources"]![0]!["AfterUpload"] = System.Text.Json.Nodes.JsonNode.Parse("""{ "OnSuccess": { "Action": "Move", "Path": "/tmp/done-elsewhere" } }""");
        var cfg = Create(machine.ToJsonString());
        var page = NewPage(cfg);

        page.Sources[0].RemotePath = "/incoming/alpha";
        Save(page);

        var source = cfg.Load().Config!.Sources[0];
        Assert.AreEqual("/incoming/alpha", source.RemotePath);
        CollectionAssert.AreEqual(new[] { "skip.txt" }, source.Ignore.Files.ToArray());
        Assert.AreEqual(MoveAction.Move, source.AfterUpload.OnSuccess.Action);
        Assert.AreEqual("/tmp/done-elsewhere", source.AfterUpload.OnSuccess.Path);
    }

    [TestMethod]
    public void A_Source_field_error_shows_on_its_row_and_disables_Save()
    {
        var page = NewPage(Create(ValidMachine().ToJsonString()));

        page.Sources[0].Name = "has space";

        StringAssert.Contains(page.Sources[0].Error, "filename-safe");
        Assert.IsFalse(CanSave(page));
    }

    [TestMethod]
    public void A_Directory_path_that_does_not_exist_only_warns()
    {
        var page = NewPage(Create(ValidMachine().ToJsonString()));

        page.Sources[0].Path = Path.Combine(Dir, "not-there-yet");

        Assert.IsFalse(page.HasErrors);
        StringAssert.Contains(page.Sources[0].Warning, "does not exist");
        Assert.IsTrue(CanSave(page));
    }

    [TestMethod]
    public void Browse_fills_the_Directory_path()
    {
        var page = NewPage(Create(ValidMachine().ToJsonString()));
        page.PickFolder = () => Task.FromResult<string?>(Path.Combine(Dir, "picked"));

        page.Sources[0].BrowseCommand.Execute().Subscribe();

        Assert.AreEqual(Path.Combine(Dir, "picked"), page.Sources[0].Path);
    }

    [TestMethod]
    public void The_Remote_Path_placeholder_shows_the_default()
    {
        var page = NewPage(Create(ValidMachine().ToJsonString()));

        Assert.AreEqual("/incoming/alpha", page.Sources[0].RemotePathPlaceholder);

        page.Field("Sftp:RemoteRoot").Value = "/drop/";
        page.Sources[0].Name = "beta";

        Assert.AreEqual("/drop/beta", page.Sources[0].RemotePathPlaceholder);
    }

    [TestMethod]
    public void Sources_from_the_environment_are_locked()
    {
        var cfg = Create(ValidMachine().ToJsonString(), env: new()
        {
            ["MIRES_Sources__0__Name"] = "envsrc", ["MIRES_Sources__0__Type"] = "Directory", ["MIRES_Sources__0__Path"] = "/tmp",
        });

        var page = NewPage(cfg);

        Assert.IsTrue(page.SourcesLocked);
        Assert.IsFalse(page.SourcesEditable);
        Assert.IsFalse(page.Sources[0].IsEditable);
        Assert.IsFalse(page.AddSourceCommand.CanExecute.FirstAsync().ToTask().Result);
    }

    // ---- Secrets ----

    [TestMethod]
    public void Secrets_show_only_set_or_not_set()
    {
        var machine = ValidMachine();
        machine["Sources"]!.AsArray().Add(System.Text.Json.Nodes.JsonNode.Parse("""{ "Name": "wsi", "Type": "S3", "Endpoint": "https://s3.example.org", "Bucket": "b" }"""));
        var cfg = Create(machine.ToJsonString(), env: new()
        {
            ["MIRES_SFTP_PASSWORD"] = "hunter2-very-secret", ["MIRES_S3_WSI_ACCESS_KEY"] = "AKIAEXAMPLE",
        });

        var page = NewPage(cfg);

        Assert.AreEqual("set", page.SftpPasswordStatus);
        Assert.AreEqual("not set", page.SftpKeyPassphraseStatus);
        StringAssert.Contains(page.Sources[1].SecretStatus, "Access key: set");
        StringAssert.Contains(page.Sources[1].SecretStatus, "Secret key: not set");
        StringAssert.Contains(page.Sources[1].SecretStatus, "MIRES_S3_WSI_SECRET_KEY");
        Assert.IsFalse(page.TryGetField("Sftp:Password", out _));
        var everything = string.Join("|", page.Fields.Select(f => f.Value)) + page.SftpPasswordStatus + page.Sources[1].SecretStatus;
        Assert.DoesNotContain("hunter2", everything);
        Assert.DoesNotContain("AKIAEXAMPLE", everything);
    }
}

using System.Reactive.Linq;
using System.Reactive.Threading.Tasks;
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
}

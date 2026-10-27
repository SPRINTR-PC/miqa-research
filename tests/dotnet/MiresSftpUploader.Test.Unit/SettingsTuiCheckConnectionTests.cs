using MiresSftpUploader.Core;
using MiresSftpUploader.Test.Support;
using Terminal.Gui.Input;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class SettingsTuiCheckConnectionTests : SettingsTuiTestBase
{
    private (SettingsTuiHarness Tui, FakeRemote Remote) StartChecking(Dictionary<string, string?>? env = null)
    {
        File.WriteAllText(MachinePath, ValidMachine().ToJsonString());
        var configuration = new Configuration(new ConfigurationLocations(MachinePath, UserPath,
            env ?? new Dictionary<string, string?> { ["MIRES_SFTP_PASSWORD"] = "pw" }));
        var tui = Start(configuration);
        var remote = new FakeRemote();
        tui.Window.ConnectionChecker = token => ConnectionCheck.CheckSavedAsync(configuration, _ => remote, token);
        tui.Window.PostToUi = action => action();
        return (tui, remote);
    }

    private static async Task<string> F5(SettingsTuiHarness tui)
    {
        tui.Press(Key.F5);
        await tui.Window.PendingCheck;
        return tui.Dialogs.Messages.Last().Message;
    }

    [TestMethod]
    public void The_key_bar_lists_F5()
    {
        var (tui, _) = StartChecking();

        Assert.IsTrue(tui.Shows("F5 Check"), tui.Screen);
    }

    [TestMethod]
    public async Task F5_connects_once_and_shows_success_in_a_dialog()
    {
        var (tui, remote) = StartChecking();

        var message = await F5(tui);

        StringAssert.Contains(message, "Connected to");
        StringAssert.Contains(message, "sftp.example.org");
        Assert.AreEqual(1, remote.ConnectCount);
    }

    [TestMethod]
    public async Task F5_shows_a_host_key_mismatch()
    {
        var (tui, remote) = StartChecking();
        remote.Inject(RemoteOperation.Connect, RemoteResult.Failed("Host key mismatch: presented SHA256:zzz"));

        StringAssert.Contains(await F5(tui), "Host key mismatch");
    }

    [TestMethod]
    public async Task F5_shows_refused_credentials()
    {
        var (tui, remote) = StartChecking();
        remote.Inject(RemoteOperation.Connect, RemoteResult.Denied("Authentication failed"));

        StringAssert.Contains(await F5(tui), "Authentication failed");
    }

    [TestMethod]
    public async Task F5_names_the_missing_credentials_without_connecting()
    {
        var (tui, remote) = StartChecking(new Dictionary<string, string?>());

        StringAssert.Contains(await F5(tui), "MIRES_SFTP_PASSWORD");
        Assert.AreEqual(0, remote.ConnectCount);
    }

    [TestMethod]
    public async Task F5_with_unsaved_changes_says_Save_first_and_does_not_connect()
    {
        var (tui, remote) = StartChecking();
        tui.Page.Field("Sftp:Port").Value = "2222";

        tui.Press(Key.F5);
        await tui.Window.PendingCheck;

        StringAssert.Contains(tui.Dialogs.Messages.Last().Message, "Save first");
        Assert.AreEqual(0, remote.ConnectCount);
    }

    [TestMethod]
    public async Task F5_after_saving_checks_the_saved_configuration()
    {
        var (tui, remote) = StartChecking();
        tui.Page.Field("Sftp:Port").Value = "2222";
        tui.Press(Key.S.WithCtrl);

        StringAssert.Contains(await F5(tui), "Connected to");
        Assert.AreEqual(1, remote.ConnectCount);
    }

    [TestMethod]
    public async Task A_check_that_throws_shows_the_message_without_Secrets()
    {
        var (tui, _) = StartChecking();
        tui.Window.Redact = text => text.Replace("hunter2-secret", Redactor.Mask);
        tui.Window.ConnectionChecker = _ => throw new InvalidOperationException("login with hunter2-secret refused");

        var message = await F5(tui);

        StringAssert.Contains(message, "refused");
        Assert.DoesNotContain("hunter2-secret", message);
    }
}

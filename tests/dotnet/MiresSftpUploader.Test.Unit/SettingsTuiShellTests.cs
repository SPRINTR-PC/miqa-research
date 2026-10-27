using MiresSftpUploader.SettingsTui;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class SettingsTuiShellTests : SettingsTuiTestBase
{
    [TestMethod]
    public void It_shows_all_eleven_pages_and_the_Destination_form()
    {
        var tui = Start();

        foreach (var title in PageCatalog.Titles) Assert.IsTrue(tui.Shows(title), $"sidebar lacks {title}\n{tui.Screen}");
        Assert.HasCount(11, PageCatalog.Titles);
        StringAssert.Contains(tui.Row("Host")!, "sftp.example.org");
        StringAssert.Contains(tui.Row("Username")!, "u");
        Assert.IsTrue(tui.Shows("Ctrl+S"), "key bar");
    }

    [TestMethod]
    public void A_command_that_fails_shows_its_message_and_the_interface_keeps_running()
    {
        var tui = Start();
        var failing = ReactiveUI.ReactiveCommand.CreateFromObservable<System.Reactive.Unit, System.Reactive.Unit>(
            _ => System.Reactive.Linq.Observable.Throw<System.Reactive.Unit>(new InvalidOperationException("disk full")));

        failing.Fire(tui.Window);

        Assert.AreEqual("disk full", tui.Dialogs.Messages.Single().Message);
        Assert.IsFalse(tui.Window.ExitRequested);
    }
}

using MiresSftpUploader.SettingsTui;

namespace MiresSftpUploader.Test.Unit;

/// <summary>Layout is only checked as "the key rows fit and nothing is clipped" at the minimum and a larger size.</summary>
[TestClass]
public sealed class SettingsTuiLayoutTests : SettingsTuiTestBase
{
    [TestMethod]
    [DataRow(80, 24)]
    [DataRow(120, 40)]
    public void The_key_rows_fit_and_the_chrome_is_not_clipped(int width, int height)
    {
        var tui = Start(width: width, height: height);
        var lines = tui.Lines;

        Assert.AreEqual(height, lines.Length);
        StringAssert.Contains(lines[0], "Settings", "header");
        StringAssert.Contains(lines[0], "User Overrides", "header is not cut off");
        StringAssert.Contains(lines[^2], "no changes", "status line");
        StringAssert.Contains(lines[^1], "Ctrl+S Save");
        StringAssert.Contains(lines[^1], "Ctrl+R Revert");
        StringAssert.Contains(lines[^1], "F4 Issues");
        StringAssert.Contains(lines[^1], "Ctrl+Q Quit");
        foreach (var title in PageCatalog.Titles) Assert.IsTrue(tui.Shows(title), title + " is clipped");
        StringAssert.Contains(tui.Row("Host")!, "sftp.example.org");
        StringAssert.Contains(tui.Row("Port")!, "22");
    }

    [TestMethod]
    public void Below_the_minimum_an_overlay_replaces_the_screen_and_the_screen_returns_when_it_grows()
    {
        var tui = Start(width: 100, height: 32);

        tui.Resize(70, 20);
        Assert.IsTrue(tui.Window.OverlayVisible);
        Assert.IsTrue(tui.Shows("at least 80x24"), tui.Screen);
        Assert.IsFalse(tui.Shows("Remote root"));

        tui.Resize(100, 32);
        Assert.IsFalse(tui.Window.OverlayVisible);
        Assert.IsTrue(tui.Shows("Remote root"));
    }

    [TestMethod]
    public void Keys_do_nothing_while_the_overlay_is_showing()
    {
        var tui = Start(width: 100, height: 32);
        tui.Resize(70, 20);

        tui.Press(Terminal.Gui.Input.Key.PageDown.WithCtrl);

        Assert.AreEqual(0, tui.Window.PageIndex);
    }

    [TestMethod]
    public void No_key_reaches_the_form_or_the_commands_while_the_overlay_is_showing()
    {
        var tui = Start(width: 100, height: 32);
        tui.Page.Field("Sftp:Port").Value = "2222";
        tui.Resize(70, 20);

        tui.Press(Terminal.Gui.Input.Key.Esc, Terminal.Gui.Input.Key.Tab, Terminal.Gui.Input.Key.Enter, Terminal.Gui.Input.Key.CursorRight,
            Terminal.Gui.Input.Key.CursorDown, Terminal.Gui.Input.Key.F4, Terminal.Gui.Input.Key.F5, Terminal.Gui.Input.Key.S.WithCtrl,
            Terminal.Gui.Input.Key.R.WithCtrl, Terminal.Gui.Input.Key.Q.WithCtrl, (Terminal.Gui.Input.Key)'x');

        Assert.IsTrue(tui.Page.HasChanges, "Ctrl+S and Ctrl+R must not run");
        Assert.AreEqual("2222", tui.Page.Field("Sftp:Port").Value);
        Assert.IsFalse(tui.Window.ExitRequested);
        Assert.IsEmpty(tui.Dialogs.UnsavedAsked);
        Assert.IsEmpty(tui.Dialogs.IssueLists);
        Assert.IsEmpty(tui.Dialogs.Messages);
        Assert.AreEqual(0, tui.Window.PageIndex);

        tui.Resize(100, 32);
        Assert.IsTrue(tui.Page.HasChanges);
        Assert.AreEqual("2222", tui.Page.Field("Sftp:Port").Value);
    }
}

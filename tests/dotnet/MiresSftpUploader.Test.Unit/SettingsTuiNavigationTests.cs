using MiresSftpUploader.SettingsTui;
using Terminal.Gui.Input;

namespace MiresSftpUploader.Test.Unit;

/// <summary>
/// The navigation and focus regression group: every pitfall found in the prototype (non-focusable containers, Tab skipping nested inputs,
/// Esc going back one level) stays fixed.
/// </summary>
[TestClass]
public sealed class SettingsTuiNavigationTests : SettingsTuiTestBase
{
    // The Host Key Fingerprint of the test configuration is set, so its text box is disabled until Unlock; Tab stops on the Unlock button instead.
    private static readonly string[] DestinationOrder =
    [
        "Host", "Port", "Username", "Authentication", "Private key file",
        "Host Key Fingerprint", "Remote root", "Remote access", "Upload strategy", "Connect timeout (seconds)", "Keep-alive (seconds)",
    ];

    private static SettingsTuiHarness EnterForm(SettingsTuiHarness tui)
    {
        tui.Press(Key.Enter);
        return tui;
    }

    [TestMethod]
    public void It_starts_with_the_focus_on_the_sidebar()
    {
        var tui = Start();

        Assert.IsTrue(tui.SidebarFocused, tui.FocusPath);
    }

    [TestMethod]
    public void Enter_Right_and_Tab_go_from_the_sidebar_into_the_form()
    {
        foreach (var key in new[] { Key.Enter, Key.CursorRight, Key.Tab })
        {
            var tui = Start();
            tui.Press(key);

            Assert.AreEqual("Host", tui.FocusedFieldLabel, $"{key}: {tui.FocusPath}");
        }
    }

    [TestMethod]
    public void Tab_visits_every_editable_field_of_the_page_in_order_and_Shift_Tab_walks_back()
    {
        var tui = EnterForm(Start());

        var forward = new List<string?> { tui.FocusedFieldLabel };
        for (var i = 1; i < DestinationOrder.Length; i++)
        {
            tui.Press(Key.Tab);
            forward.Add(tui.FocusedFieldLabel);
        }

        Assert.AreEqual(string.Join(" > ", DestinationOrder), string.Join(" > ", forward));

        var back = new List<string?> { tui.FocusedFieldLabel };
        for (var i = 1; i < DestinationOrder.Length; i++)
        {
            tui.Press(Key.Tab.WithShift);
            back.Add(tui.FocusedFieldLabel);
        }

        CollectionAssert.AreEqual(DestinationOrder.Reverse().ToArray(), back);
    }

    [TestMethod]
    public void Down_and_Up_move_between_single_line_fields_like_Tab()
    {
        var tui = EnterForm(Start());

        tui.Press(Key.CursorDown);
        Assert.AreEqual("Port", tui.FocusedFieldLabel);
        tui.Press(Key.CursorUp);
        Assert.AreEqual("Host", tui.FocusedFieldLabel);
    }

    [TestMethod]
    public void Esc_goes_back_one_level_and_never_quits()
    {
        var tui = EnterForm(Start());
        tui.Press(Key.Tab);

        tui.Press(Key.Esc);
        Assert.IsTrue(tui.SidebarFocused, "form to sidebar: " + tui.FocusPath);

        tui.Press(Key.Esc);
        Assert.IsTrue(tui.SidebarFocused);
        Assert.IsFalse(tui.Window.ExitRequested, "Esc at the top level does nothing; Ctrl+Q quits");
    }

    [TestMethod]
    public void Shift_Tab_on_the_first_field_does_not_lose_the_focus()
    {
        var tui = EnterForm(Start());

        tui.Press(Key.Tab.WithShift);

        Assert.IsNotNull(tui.Focused, "focus must land somewhere");
        // Wrapping backwards from the first field lands on the page's last control, which on Destination is the Check connection button.
        Assert.IsTrue(tui.SidebarFocused || tui.FocusedFieldLabel is not null || tui.Focused is Terminal.Gui.Views.Button, tui.FocusPath);
    }

    [TestMethod]
    public void Typing_in_a_field_keeps_the_focus_and_writes_the_view_model()
    {
        var tui = EnterForm(Start());
        tui.TabTo("Username");

        tui.Type("ser");

        Assert.AreEqual("Username", tui.FocusedFieldLabel);
        StringAssert.Contains(tui.Page.Field("Sftp:Username").Value, "ser");
    }

    [TestMethod]
    public void Ctrl_PageDown_and_Ctrl_PageUp_change_the_page_and_the_content_follows()
    {
        var tui = Start();

        tui.Press(Key.PageDown.WithCtrl);
        Assert.AreEqual(1, tui.Window.PageIndex);
        Assert.AreEqual("Secrets", tui.Window.Body.Title);
        Assert.IsFalse(tui.Shows("Remote root"), "the Destination form is gone");

        tui.Press(Key.PageUp.WithCtrl);
        Assert.AreEqual("Destination", tui.Window.Body.Title);
        Assert.IsTrue(tui.Shows("Remote root"));
    }

    [TestMethod]
    public void Moving_the_sidebar_selection_shows_that_page()
    {
        var tui = Start();

        tui.Press(Key.CursorDown);

        Assert.AreEqual("Secrets", tui.Window.Body.Title);
        Assert.IsTrue(tui.SidebarFocused, "browsing the sidebar keeps the focus there");
    }
}

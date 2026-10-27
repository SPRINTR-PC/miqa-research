using MiresSftpUploader.SettingsTui;
using Terminal.Gui.Input;

namespace MiresSftpUploader.Test.Unit;

/// <summary>Editing, validation, Save, Revert, the quit flow and Locked Settings through the keyboard. Settings logic itself is covered by the view-model tests.</summary>
[TestClass]
public sealed class SettingsTuiEditingTests : SettingsTuiTestBase
{
    private static void Replace(SettingsTuiHarness tui, string text)
    {
        tui.Press(Key.A.WithCtrl);
        tui.Press(Key.Delete);
        tui.Type(text);
    }

    private static SettingsTuiHarness EditPort(SettingsTuiHarness tui, string value)
    {
        tui.Press(Key.Enter);
        tui.TabTo("Port");
        Replace(tui, value);
        return tui;
    }

    [TestMethod]
    public void Editing_a_field_changes_the_view_model_and_marks_the_row_the_page_and_the_status()
    {
        var tui = EditPort(Start(), "2222");

        Assert.AreEqual("2222", tui.Page.Field("Sftp:Port").Value);
        StringAssert.Contains(tui.Row("Port")!, "●");
        Assert.AreEqual("● Destination", tui.SidebarRow("Destination"));
        StringAssert.Contains(tui.Window.StatusText, "unsaved changes");
    }

    [TestMethod]
    public void An_invalid_value_shows_an_inline_error_marks_the_page_and_turns_the_status_to_problems()
    {
        var tui = EditPort(Start(), "abc");

        Assert.IsTrue(tui.Page.Field("Sftp:Port").HasError);
        Assert.IsTrue(tui.Shows("✗"), "inline error marker\n" + tui.Screen);
        Assert.AreEqual("! Destination", tui.SidebarRow("Destination"));
        StringAssert.Contains(tui.Window.StatusText, "Save is disabled");
    }

    [TestMethod]
    public void Ctrl_S_is_ignored_while_an_error_exists()
    {
        var tui = EditPort(Start(), "abc");
        var before = File.ReadAllText(MachinePath);

        tui.Press(Key.S.WithCtrl);

        Assert.AreEqual(before, File.ReadAllText(MachinePath));
        Assert.IsTrue(tui.Page.HasChanges);
    }

    [TestMethod]
    public void Ctrl_S_writes_Destination_to_the_Machine_Config_and_the_rest_to_User_Overrides()
    {
        var tui = EditPort(Start(), "2222");
        tui.Page.Field("Upload:MaxParallelUploads").Value = "7";

        tui.Press(Key.S.WithCtrl);

        StringAssert.Contains(File.ReadAllText(MachinePath), "2222");
        StringAssert.Contains(File.ReadAllText(UserPath), "MaxParallelUploads");
        Assert.IsFalse(File.ReadAllText(UserPath).Contains("2222"), "the Destination is not a User Override");
        StringAssert.Contains(tui.Window.StatusText, "no changes");
        Assert.IsFalse(tui.Shows("●") && tui.Row("Port")!.Contains('●'), "the changed marker is gone");
    }

    [TestMethod]
    public void Saving_keeps_the_focus_in_the_form()
    {
        var tui = EditPort(Start(), "2222");

        tui.Press(Key.S.WithCtrl);

        Assert.IsNotNull(tui.FocusedFieldLabel, tui.FocusPath);
    }

    [TestMethod]
    public void Ctrl_R_reverts_the_edit_and_the_screen_shows_the_original_value()
    {
        var tui = EditPort(Start(), "2222");

        tui.Press(Key.R.WithCtrl);

        Assert.AreEqual("22", tui.Page.Field("Sftp:Port").Value);
        StringAssert.Contains(tui.Row("Port")!, "22");
        Assert.IsFalse(tui.Row("Port")!.Contains('●'));
        StringAssert.Contains(tui.Window.StatusText, "no changes");
    }

    [TestMethod]
    public void Quit_without_changes_stops_at_once_without_asking()
    {
        var tui = Start();

        tui.Press(Key.Q.WithCtrl);

        Assert.IsTrue(tui.Window.ExitRequested);
        Assert.IsEmpty(tui.Dialogs.UnsavedAsked);
        Assert.AreEqual(0, tui.Window.ExitCode);
    }

    [TestMethod]
    public void Quit_with_changes_asks_and_Cancel_stays()
    {
        var tui = EditPort(Start(), "2222");

        tui.Press(Key.Q.WithCtrl);

        CollectionAssert.AreEqual(new[] { true }, tui.Dialogs.UnsavedAsked);
        Assert.IsFalse(tui.Window.ExitRequested);
        Assert.AreEqual("2222", tui.Page.Field("Sftp:Port").Value);
    }

    [TestMethod]
    public void Quit_Discard_stops_without_writing()
    {
        var dialogs = new FakeTuiDialogs();
        dialogs.UnsavedAnswers.Enqueue(UnsavedChoice.Discard);
        var tui = EditPort(Start(dialogs: dialogs), "2222");
        var before = File.ReadAllText(MachinePath);

        tui.Press(Key.Q.WithCtrl);

        Assert.IsTrue(tui.Window.ExitRequested);
        Assert.AreEqual(before, File.ReadAllText(MachinePath));
    }

    [TestMethod]
    public void Quit_Save_writes_and_stops()
    {
        var dialogs = new FakeTuiDialogs();
        dialogs.UnsavedAnswers.Enqueue(UnsavedChoice.Save);
        var tui = EditPort(Start(dialogs: dialogs), "2222");

        tui.Press(Key.Q.WithCtrl);

        Assert.IsTrue(tui.Window.ExitRequested);
        StringAssert.Contains(File.ReadAllText(MachinePath), "2222");
    }

    [TestMethod]
    public void Quit_with_errors_offers_no_Save()
    {
        var tui = EditPort(Start(), "abc");

        tui.Press(Key.Q.WithCtrl);

        CollectionAssert.AreEqual(new[] { false }, tui.Dialogs.UnsavedAsked);
        Assert.IsFalse(tui.Window.ExitRequested);
    }

    [TestMethod]
    public void A_termination_signal_exits_130_and_saves_nothing()
    {
        var tui = EditPort(Start(), "2222");
        var before = File.ReadAllText(MachinePath);

        tui.Window.Terminate();

        Assert.IsTrue(tui.Window.ExitRequested);
        Assert.AreEqual(130, tui.Window.ExitCode);
        Assert.AreEqual(before, File.ReadAllText(MachinePath));
        Assert.IsEmpty(tui.Dialogs.UnsavedAsked, "no question on a dropped session");
    }

    [TestMethod]
    public void F4_lists_every_problem()
    {
        var tui = EditPort(Start(), "abc");

        tui.Press(Key.F4);

        Assert.HasCount(1, tui.Dialogs.IssueLists);
        Assert.IsTrue(tui.Dialogs.IssueLists[0].Any(l => l.StartsWith("✗ Port")), string.Join("\n", tui.Dialogs.IssueLists[0]));
    }

    [TestMethod]
    public void A_setting_from_the_environment_is_disabled_with_its_reason_and_Tab_skips_it()
    {
        var cfg = Create(ValidMachine().ToJsonString(), env: new() { ["MIRES_Sftp__Host"] = "env.example.org" });
        var tui = Start(cfg);

        StringAssert.Contains(tui.Row("🔒")!, "environment");
        Assert.AreEqual("L Destination", tui.SidebarRow("Destination"));
        tui.Press(Key.Enter);
        Assert.AreEqual("Port", tui.FocusedFieldLabel, "the locked Host is not an input stop");
    }

    [TestMethod]
    public void The_Host_Key_Fingerprint_unlocks_only_after_the_confirmation_dialog()
    {
        var dialogs = new FakeTuiDialogs();
        var tui = Start(dialogs: dialogs);
        tui.Press(Key.Enter);
        tui.TabTo("Host Key Fingerprint");

        tui.Press(Key.Enter); // Unlock, answer: Cancel
        Assert.HasCount(1, dialogs.Confirmations);
        Assert.IsFalse(tui.Page.Field("Sftp:HostKeyFingerprint").IsEditable);

        dialogs.ConfirmAnswers.Enqueue(true);
        tui.Press(Key.Enter);
        Assert.IsTrue(tui.Page.Field("Sftp:HostKeyFingerprint").IsEditable);
    }

    [TestMethod]
    public void The_Unlock_question_and_the_disabled_fingerprint_box_match_the_UI()
    {
        var dialogs = new FakeTuiDialogs();
        var tui = Start(dialogs: dialogs);
        tui.Press(Key.Enter);
        tui.TabTo("Host Key Fingerprint");
        StringAssert.Contains(tui.Row("Host Key Fingerprint")!, "Unlock");

        // Disabled until Unlock: the answer Cancel leaves the box disabled and the value alone.
        var row = tui.FieldRowFor("Host Key Fingerprint");
        Assert.IsFalse(row.Input.Enabled);
        tui.Press(Key.Enter);
        Assert.AreEqual("Change the Host Key Fingerprint?", dialogs.Confirmations[0].Title);
        StringAssert.Contains(dialogs.Confirmations[0].Message, "pins the identity of the SFTP server");
        Assert.IsFalse(row.Input.Enabled);

        dialogs.ConfirmAnswers.Enqueue(true);
        tui.Press(Key.Enter);
        Assert.IsTrue(row.Input.Enabled);
        Assert.HasCount(2, dialogs.Confirmations);
    }

    [TestMethod]
    public void Folder_picking_and_the_clipboard_stay_unwired()
    {
        var tui = Start();
        var defaults = new MiresSftpUploader.ViewModels.SettingsPageViewModel(Create(ValidMachine().ToJsonString()));
        Assert.IsNull(tui.Page.PickFolder().GetAwaiter().GetResult());
        Assert.AreSame(defaults.PickFolder.Method, tui.Page.PickFolder.Method);
        Assert.AreSame(defaults.CopyToClipboard.Method, tui.Page.CopyToClipboard.Method);
    }

    [TestMethod]
    public void It_starts_on_an_invalid_configuration_and_says_so()
    {
        var cfg = Create("{}");
        var tui = Start(cfg);

        Assert.IsTrue(tui.Page.HasErrors);
        StringAssert.Contains(tui.Window.StatusText, "problem");
        tui.Press(Key.Enter);
        Assert.AreEqual("Host", tui.FocusedFieldLabel);
    }

    [TestMethod]
    public void The_header_reports_an_unusable_Data_Directory()
    {
        var cfg = Create(ValidMachine().ToJsonString());
        var page = new MiresSftpUploader.ViewModels.SettingsPageViewModel(cfg,
            path => new MiresSftpUploader.Core.DataDirectoryAccess(path, false, false, "a", "g", 1, 1, false, "sudo fix", "cannot be used"), _ => long.MaxValue);

        var tui = Start(cfg, page: page);

        StringAssert.Contains(tui.Lines[0], "Data Directory cannot be used");
    }
}

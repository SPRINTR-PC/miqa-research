using MiresSftpUploader.Core;
using MiresSftpUploader.SettingsTui;
using MiresSftpUploader.SettingsTui.Pages;
using Terminal.Gui.Input;
using Terminal.Gui.ViewBase;
using Terminal.Gui.Views;

namespace MiresSftpUploader.Test.Unit;

/// <summary>The Sources page: list with Add/Remove, type-adaptive form, locked list, per-Source Archive Rules dialog.</summary>
[TestClass]
public sealed class SettingsTuiSourcesTests : SettingsTuiTestBase
{
    private SettingsTuiHarness OpenSources(Configuration? cfg = null, FakeTuiDialogs? dialogs = null)
    {
        var tui = Start(cfg, dialogs: dialogs);
        tui.Window.PageIndex = PageCatalog.Titles.ToList().IndexOf("Sources");
        tui.Draw();
        return tui;
    }

    /// <summary>The label of the form row (or button) holding the focus on a master/detail page.</summary>
    private static string? FocusedRow(SettingsTuiHarness tui)
    {
        var f = tui.Focused;
        if (f is Button b) return "[" + b.Text.Trim() + "]";
        if (f is ListView) return "<list>";
        return f?.SuperView?.SubViews.OfType<Label>().FirstOrDefault()?.Text.Trim();
    }

    private const string RulesButton = "[Archive Rules for this Source (0)…]";

    [TestMethod]
    public void It_lists_the_Sources_and_shows_the_form_of_the_selected_one()
    {
        var tui = OpenSources();

        Assert.IsTrue(tui.Shows("alpha [Directory]"), tui.Screen);
        Assert.IsTrue(tui.Shows("Directory path"), tui.Screen);
        Assert.IsTrue(tui.Shows("Remote Path"), tui.Screen);
    }

    [TestMethod]
    public void Add_selects_the_new_Source_and_puts_the_cursor_in_its_Name()
    {
        var tui = OpenSources();
        tui.Press(Key.Enter); // into the list
        tui.Press(Key.Tab);   // Add
        Assert.AreEqual("[Add]", FocusedRow(tui));

        tui.Press(Key.Enter);

        Assert.AreEqual(2, tui.Page.Sources.Count);
        Assert.IsTrue(tui.Shows("(new) [Directory]"), tui.Screen);
        Assert.AreEqual("Name", FocusedRow(tui), tui.FocusPath);
        Assert.IsInstanceOfType<TextField>(tui.Focused);
    }

    [TestMethod]
    public void Typing_a_Name_updates_the_list_row_and_keeps_the_focus()
    {
        var tui = OpenSources();
        tui.Press(Key.Enter, Key.Tab, Key.Enter);

        tui.Type("scanner");

        Assert.AreEqual("scanner", tui.Page.Sources[1].Name);
        Assert.IsTrue(tui.Shows("scanner [Directory]"), tui.Screen);
        Assert.AreEqual("Name", FocusedRow(tui));
        Assert.AreEqual("scanner", tui.FocusedText);
    }

    [TestMethod]
    public void Tab_reaches_every_control_in_order_and_Shift_Tab_walks_back()
    {
        var tui = OpenSources();
        tui.Press(Key.Enter);
        var order = new List<string?> { FocusedRow(tui) };
        for (var i = 0; i < 8; i++)
        {
            tui.Press(Key.Tab);
            // A directory path typed in full takes the first Tab to append its separator.
            if (FocusedRow(tui) == "Directory path" && order[^1] == "Directory path") tui.Press(Key.Tab);
            order.Add(FocusedRow(tui));
        }

        CollectionAssert.AreEqual(
            new[] { "<list>", "[Add]", "[Remove]", "Name", "Type", "Enabled", "Directory path", "Remote Path (optional)", RulesButton },
            order.ToArray(), tui.FocusPath);

        for (var i = 0; i < 6; i++) tui.Press(Key.Tab.WithShift);
        Assert.AreEqual("[Remove]", FocusedRow(tui));
    }

    [TestMethod]
    public void Esc_goes_form_to_list_to_sidebar()
    {
        var tui = OpenSources();
        tui.Press(Key.Enter, Key.Enter); // sidebar -> list -> form (Name)
        Assert.AreEqual("Name", FocusedRow(tui));

        tui.Press(Key.Esc);
        Assert.AreEqual("<list>", FocusedRow(tui), tui.FocusPath);

        tui.Press(Key.Esc);
        Assert.IsTrue(tui.SidebarFocused, tui.FocusPath);
    }

    [TestMethod]
    public void Changing_the_Type_rebuilds_the_form_for_S3_and_back()
    {
        var tui = OpenSources();
        tui.Press(Key.Enter, Key.Enter, Key.Tab);
        Assert.AreEqual("Type", FocusedRow(tui));

        tui.Page.Sources[0].Type = Core.SourceType.S3;
        tui.Draw();

        Assert.IsTrue(tui.Shows("Endpoint URL"), tui.Screen);
        Assert.IsTrue(tui.Shows("Bucket"));
        Assert.IsTrue(tui.Shows("Force path style"));
        Assert.IsFalse(tui.Shows("Directory path"));

        tui.Page.Sources[0].Type = Core.SourceType.Directory;
        tui.Draw();
        Assert.IsTrue(tui.Shows("Directory path"));
        Assert.IsFalse(tui.Shows("Endpoint URL"));
    }

    [TestMethod]
    public void Choosing_S3_in_the_Type_drop_down_rebuilds_the_form_and_keeps_the_focus_on_Type()
    {
        var tui = OpenSources();
        tui.Press(Key.Enter, Key.Enter, Key.Tab);

        tui.Press(Key.Enter); // open the drop-down
        tui.Press(Key.CursorDown, Key.Enter);
        tui.Draw();

        Assert.AreEqual(Core.SourceType.S3, tui.Page.Sources[0].Type);
        Assert.IsTrue(tui.Shows("Endpoint URL"), tui.Screen);
        Assert.AreEqual("Type", FocusedRow(tui), tui.FocusPath);
    }

    [TestMethod]
    public void Remove_deletes_the_selected_Source_and_the_form_goes_away()
    {
        var tui = OpenSources();
        tui.Press(Key.Enter, Key.Tab, Key.Tab, Key.Enter); // Remove

        Assert.AreEqual(0, tui.Page.Sources.Count);
        Assert.IsFalse(tui.Shows("alpha [Directory]"));
        Assert.IsFalse(tui.Shows("Directory path"));
    }

    [TestMethod]
    public void A_locked_Sources_list_disables_Add_and_Remove_and_says_why()
    {
        var cfg = Create(ValidMachine().ToJsonString(), env: new()
        {
            ["MIRES_Sources__0__Name"] = "envsrc", ["MIRES_Sources__0__Type"] = "Directory", ["MIRES_Sources__0__Path"] = "/tmp",
        });
        var tui = OpenSources(cfg);

        Assert.IsTrue(tui.Shows("🔒"), tui.Screen);
        tui.Press(Key.Enter, Key.Tab);
        Assert.AreNotEqual("[Add]", FocusedRow(tui), "Add is disabled");
        Assert.AreNotEqual("[Remove]", FocusedRow(tui), "Remove is disabled");
        Assert.IsTrue(tui.Shows("envsrc [Directory]"));
    }

    [TestMethod]
    public void The_Archive_Rules_button_asks_the_dialog_seam_for_that_Sources_rules()
    {
        var dialogs = new FakeTuiDialogs();
        var tui = OpenSources(dialogs: dialogs);
        tui.Press(Key.Enter, Key.Enter);
        for (var i = 0; i < 10 && FocusedRow(tui) != RulesButton; i++) tui.Press(Key.Tab);

        tui.Press(Key.Enter);

        Assert.AreEqual(1, dialogs.ArchiveRuleDialogs.Count);
        Assert.AreSame(tui.Page.Sources[0].ArchiveRules, dialogs.ArchiveRuleDialogs[0].Rules);
        StringAssert.Contains(dialogs.ArchiveRuleDialogs[0].Title, "alpha");
    }

    [TestMethod]
    public void The_Archive_Rules_dialog_content_adds_a_rule_and_edits_its_name()
    {
        var tui = OpenSources();
        var rules = tui.Page.Sources[0].ArchiveRules;
        using var content = SourceArchiveRulesEditor.Build(tui.App, rules, _ => { });
        var add = content.SubViews.OfType<Button>().First(b => b.Text.Contains("Add"));

        add.InvokeCommand(Command.Accept);

        Assert.AreEqual(1, rules.Rules.Count);
        var name = Descend(content).OfType<TextField>().First();
        name.Text = "scans";
        Assert.AreEqual("scans", rules.Rules[0].Name);

        static IEnumerable<View> Descend(View v) => new[] { v }.Concat(v.SubViews.SelectMany(Descend));
    }

    [TestMethod]
    public void The_status_line_and_sidebar_badge_follow_Source_edits()
    {
        var tui = OpenSources();
        tui.Press(Key.Enter, Key.Enter);

        tui.Type("x");

        StringAssert.Contains(tui.Window.StatusText, "unsaved");
        StringAssert.Contains(tui.SidebarRow("Sources"), "●");
    }
}

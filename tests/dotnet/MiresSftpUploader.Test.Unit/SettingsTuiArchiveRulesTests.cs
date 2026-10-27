using System.Text.Json.Nodes;
using MiresSftpUploader.SettingsTui;
using Terminal.Gui.Input;
using Terminal.Gui.ViewBase;
using Terminal.Gui.Views;

namespace MiresSftpUploader.Test.Unit;

/// <summary>The Archive Rules page: a list in added order with a form beside it. Rule logic itself is covered by the view-model tests.</summary>
[TestClass]
public sealed class SettingsTuiArchiveRulesTests : SettingsTuiTestBase
{
    private const int RulesPage = 6;

    private SettingsTuiHarness StartRules(params (string Name, string Pattern)[] rules)
    {
        var machine = ValidMachine();
        if (rules.Length > 0)
        {
            var array = new JsonArray();
            foreach (var (name, pattern) in rules) array.Add(new JsonObject { ["Name"] = name, ["Pattern"] = pattern });
            machine["Archive"] = new JsonObject { ["Rules"] = array };
        }

        var tui = Start(Create(machine.ToJsonString()));
        tui.Window.PageIndex = RulesPage;
        tui.Draw();
        return tui;
    }

    private static void Replace(SettingsTuiHarness tui, string text)
    {
        tui.Press(Key.A.WithCtrl);
        tui.Press(Key.Delete);
        tui.Type(text);
    }

    private static void PressButton(SettingsTuiHarness tui, string text)
    {
        var button = Descendants(tui.Window.Body).OfType<Button>().First(b => b.Text.Contains(text));
        button.SetFocus();
        tui.Press(Key.Enter);
    }

    private static IEnumerable<View> Descendants(View root) =>
        root.SubViews.SelectMany(v => new[] { v }.Concat(Descendants(v)));

    [TestMethod]
    public void The_page_lists_the_rules_in_added_order_and_shows_the_first_one_in_the_form()
    {
        var tui = StartRules(("dicom", @"\.dcm$"), ("logs", @"\.log$"));

        var lines = tui.Lines;
        var dicom = Array.FindIndex(lines, l => l.Contains("dicom"));
        var logs = Array.FindIndex(lines, l => l.Contains("logs"));
        Assert.IsTrue(dicom >= 0 && logs > dicom, tui.Screen);
        Assert.IsTrue(tui.Shows(@"\.dcm$"), tui.Screen);
    }

    [TestMethod]
    public void Add_selects_the_new_rule_with_the_cursor_in_its_name()
    {
        var tui = StartRules(("dicom", @"\.dcm$"));
        tui.Press(Key.Enter);

        PressButton(tui, "Add");

        Assert.HasCount(2, tui.Page.ArchiveRules.Rules);
        Assert.IsTrue(tui.Shows("(new rule)"), tui.Screen);
        Assert.IsInstanceOfType<TextField>(tui.Focused);
        tui.Type("logs");
        Assert.AreEqual("logs", tui.Page.ArchiveRules.Rules[1].Name);
        Assert.AreEqual("dicom", tui.Page.ArchiveRules.Rules[0].Name);
    }

    [TestMethod]
    public void Typing_a_name_keeps_the_cursor_updates_the_list_and_marks_the_page_and_status()
    {
        var tui = StartRules(("dicom", @"\.dcm$"));
        tui.Press(Key.Enter, Key.Enter);
        Assert.IsInstanceOfType<TextField>(tui.Focused, tui.FocusPath);

        Replace(tui, "scans");

        Assert.IsInstanceOfType<TextField>(tui.Focused, tui.FocusPath);
        Assert.AreEqual("scans", tui.FocusedText);
        Assert.AreEqual("scans", tui.Page.ArchiveRules.Rules[0].Name);
        Assert.IsTrue(tui.Lines.Any(l => l.Contains("scans") && l.StartsWith('│')), tui.Screen);
        Assert.AreEqual("● Archive Rules", tui.SidebarRow("Archive Rules"));
        StringAssert.Contains(tui.Window.StatusText, "unsaved changes");
    }

    [TestMethod]
    public void Tab_walks_the_five_rule_fields_and_Esc_goes_back_to_the_list_and_then_the_sidebar()
    {
        var tui = StartRules(("dicom", @"\.dcm$"));
        tui.Press(Key.Enter, Key.Enter);

        var visited = new List<string?>();
        for (var i = 0; i < 5; i++)
        {
            visited.Add(tui.Focused is TextField t ? t.Text : tui.Focused?.GetType().Name);
            if (i < 4) tui.Press(Key.Tab);
        }

        Assert.AreEqual(@"dicom | \.dcm$ | PerDirectory | {rule}-{dir}.zip | 1", string.Join(" | ", visited), tui.FocusPath);

        tui.Press(Key.Esc);
        Assert.IsInstanceOfType<ListView>(tui.Focused, tui.FocusPath);
        Assert.IsFalse(tui.SidebarFocused);
        tui.Press(Key.Esc);
        Assert.IsTrue(tui.SidebarFocused, tui.FocusPath);
    }

    [TestMethod]
    public void Selecting_another_rule_shows_its_fields()
    {
        var tui = StartRules(("dicom", @"\.dcm$"), ("logs", @"\.log$"));
        tui.Press(Key.Enter);
        Assert.IsInstanceOfType<ListView>(tui.Focused, tui.FocusPath);

        tui.Press(Key.CursorDown);

        Assert.IsTrue(tui.Shows(@"\.log$"), tui.Screen);
        Assert.IsFalse(tui.Shows(@"\.dcm$ "), tui.Screen);
    }

    [TestMethod]
    public void Remove_deletes_the_selected_rule_selects_a_neighbour_and_marks_the_page()
    {
        var tui = StartRules(("dicom", @"\.dcm$"), ("logs", @"\.log$"));
        tui.Press(Key.Enter);

        PressButton(tui, "Remove");

        Assert.HasCount(1, tui.Page.ArchiveRules.Rules);
        Assert.AreEqual("logs", tui.Page.ArchiveRules.Rules[0].Name);
        Assert.IsFalse(tui.Shows("dicom"), tui.Screen);
        Assert.IsTrue(tui.Shows(@"\.log$"), tui.Screen);
        Assert.AreEqual("● Archive Rules", tui.SidebarRow("Archive Rules"));
    }

    [TestMethod]
    public void Removing_the_last_rule_shows_the_empty_list_and_an_empty_form()
    {
        var tui = StartRules(("dicom", @"\.dcm$"));
        tui.Press(Key.Enter);

        PressButton(tui, "Remove");

        Assert.IsEmpty(tui.Page.ArchiveRules.Rules);
        Assert.IsTrue(tui.Shows("no rules"), tui.Screen);
        Assert.IsFalse(tui.Shows("Rule name"), tui.Screen);
    }

    [TestMethod]
    public void An_invalid_pattern_shows_an_error_marks_the_page_and_disables_Save()
    {
        var tui = StartRules(("dicom", @"\.dcm$"));
        tui.Press(Key.Enter, Key.Enter, Key.Tab);

        Replace(tui, "[");

        Assert.IsTrue(tui.Page.ArchiveRules.HasError, "the view model rejects the pattern");
        Assert.IsTrue(tui.Shows("✗"), tui.Screen);
        Assert.AreEqual("! Archive Rules", tui.SidebarRow("Archive Rules"));
        StringAssert.Contains(tui.Window.StatusText, "Save is disabled");
    }

    [TestMethod]
    public void Save_writes_the_rules_and_Revert_restores_them()
    {
        var tui = StartRules(("dicom", @"\.dcm$"));
        tui.Press(Key.Enter, Key.Enter);
        Replace(tui, "scans");

        tui.Press(Key.R.WithCtrl);
        Assert.AreEqual("dicom", tui.Page.ArchiveRules.Rules[0].Name);
        Assert.IsTrue(tui.Shows("dicom"), tui.Screen);
        Assert.AreEqual("  Archive Rules", tui.SidebarRow("Archive Rules"));

        Assert.IsInstanceOfType<ListView>(tui.Focused, "a rebuilt master/detail page puts the focus on its list\n" + tui.FocusPath);
        tui.Press(Key.Enter);
        Replace(tui, "scans");
        tui.Press(Key.S.WithCtrl);
        var written = string.Concat(Directory.GetFiles(Dir, "*.json", SearchOption.AllDirectories).Select(File.ReadAllText));
        StringAssert.Contains(written, "scans");
        Assert.AreEqual("scans", tui.Page.ArchiveRules.Rules[0].Name);
    }

    [TestMethod]
    public void Locked_rules_are_read_only_with_the_reason_and_Add_and_Remove_disabled()
    {
        var cfg = Create(ValidMachine().ToJsonString(), env: new() { ["MIRES_Archive__Rules__0__Name"] = "env", ["MIRES_Archive__Rules__0__Pattern"] = "x" });
        var tui = Start(cfg);
        tui.Window.PageIndex = RulesPage;
        tui.Draw();

        Assert.IsTrue(tui.Page.ArchiveRules.IsLocked);
        Assert.IsTrue(tui.Shows("🔒"), tui.Screen);
        Assert.AreEqual("L Archive Rules", tui.SidebarRow("Archive Rules"));
        Assert.IsFalse(Descendants(tui.Window.Body).OfType<Button>().First(b => b.Text.Contains("Add")).Enabled);
        Assert.IsFalse(Descendants(tui.Window.Body).OfType<Button>().First(b => b.Text.Contains("Remove")).Enabled);
        Assert.IsFalse(Descendants(tui.Window.Body).OfType<TextField>().First().Enabled);
    }
}

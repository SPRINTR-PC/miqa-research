using MiresSftpUploader.SettingsTui;
using Terminal.Gui.Input;
using Terminal.Gui.Views;

namespace MiresSftpUploader.Test.Unit;

/// <summary>The pages that are just a group of fields (Upload, Ignore Rules, Archives, Manifest, Reports and logs, Appearance), one test per field kind.</summary>
[TestClass]
public sealed class SettingsTuiGroupPagesTests : SettingsTuiTestBase
{
    private static readonly string[] GroupPages = ["Upload", "Ignore Rules", "Archives", "Manifest", "Reports and logs", "Appearance"];

    private static SettingsTuiHarness Open(SettingsTuiHarness tui, string page)
    {
        var target = PageCatalog.Titles.ToList().IndexOf(page);
        for (var i = 0; i < 20 && tui.Window.PageIndex < target; i++) tui.Press(Key.PageDown.WithCtrl);
        Assert.AreEqual(target, tui.Window.PageIndex);
        tui.Press(Key.Enter);
        return tui;
    }

    private static void Replace(SettingsTuiHarness tui, string text)
    {
        tui.Press(Key.A.WithCtrl);
        tui.Press(Key.Delete);
        tui.Type(text);
    }

    [TestMethod]
    public void Every_group_page_shows_all_its_fields_and_Tab_reaches_each_one_by_keyboard()
    {
        foreach (var page in GroupPages)
        {
            var tui = Open(Start(height: 60), page);
            var expected = tui.Page.Fields.Where(f => f.Group == page && f.IsEditable).Select(f => f.Label).ToList();
            Assert.IsNotEmpty(expected, page);

            foreach (var label in expected)
            {
                tui.TabTo(label);
                Assert.IsTrue(tui.Shows(label.Length > 40 ? label[..40] : label), $"{page}: {label}\n{tui.Screen}");
            }
        }
    }

    [TestMethod]
    public void A_number_field_edits_and_shows_an_inline_error_for_a_bad_value()
    {
        var tui = Open(Start(), "Upload");
        tui.TabTo("Parallel uploads");

        Replace(tui, "7");
        Assert.AreEqual("7", tui.Page.Field("Upload:MaxParallelUploads").Value);

        Replace(tui, "99");
        Assert.IsTrue(tui.Page.Field("Upload:MaxParallelUploads").HasError);
        Assert.IsTrue(tui.Shows("✗"), tui.Screen);
    }

    [TestMethod]
    public void A_toggle_flips_with_Space()
    {
        var tui = Open(Start(), "Upload");
        tui.TabTo("Rehash all files");
        var before = tui.Page.Field("Upload:RehashAll").BoolValue;

        tui.Press(Key.Space);

        Assert.AreNotEqual(before, tui.Page.Field("Upload:RehashAll").BoolValue);
    }

    [TestMethod]
    public void A_choice_changes_by_keyboard()
    {
        var tui = Open(Start(), "Appearance");
        tui.TabTo("Theme");
        var before = tui.Page.Field("Ui:Theme").Value;

        tui.Press(Key.CursorDown);
        tui.Press(Key.Enter);

        Assert.AreNotEqual(before, tui.Page.Field("Ui:Theme").Value, tui.Screen);
    }

    [TestMethod]
    public void The_Appearance_page_says_the_Theme_applies_to_the_window_only()
    {
        var tui = Open(Start(height: 40), "Appearance");

        StringAssert.Contains(tui.Screen, "Applies to the window; the terminal UI uses its own colours.");
    }

    [TestMethod]
    public void A_Lines_field_is_a_multi_line_box_with_one_entry_per_line()
    {
        var tui = Open(Start(height: 60), "Ignore Rules");
        tui.TabTo("Ignored files (one relative path per line)");
        Assert.IsInstanceOfType<TextView>(tui.Focused);

        tui.Type("a.txt");
        tui.Press(Key.Enter);
        tui.Type("b/c.txt");

        Assert.AreEqual("a.txt\nb/c.txt", tui.Page.Field("Ignore:Files").Value.Replace("\r", ""), $"focused='{tui.FocusedText}'\n{tui.Screen}");
        Assert.AreEqual("● Ignore Rules", tui.SidebarRow("Ignore Rules"));
    }

    [TestMethod]
    public void A_path_field_is_typed()
    {
        var tui = Open(Start(), "Reports and logs");
        tui.TabTo("Report directory");

        Replace(tui, "/var/reports");

        Assert.AreEqual("/var/reports", tui.Page.Field("Report:Directory").Value);
    }

    [TestMethod]
    public void Help_text_sits_under_the_field()
    {
        var tui = Open(Start(), "Upload");

        Assert.IsTrue(tui.Shows("1 to 16 files at a time."), tui.Screen);
    }

    [TestMethod]
    public void Sidebar_badges_update_live_without_stealing_the_focus()
    {
        var tui = Open(Start(), "Upload");
        tui.TabTo("Parallel uploads");

        Replace(tui, "99");
        Assert.AreEqual("! Upload", tui.SidebarRow("Upload"));
        Assert.AreEqual("Parallel uploads", tui.FocusedFieldLabel);

        Replace(tui, "5");
        Assert.AreEqual("● Upload", tui.SidebarRow("Upload"));
        Assert.AreEqual("Parallel uploads", tui.FocusedFieldLabel);
    }
}

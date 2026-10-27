using MiresSftpUploader.SettingsTui;
using Terminal.Gui.Input;
using Terminal.Gui.Views;

namespace MiresSftpUploader.Test.Unit;

/// <summary>Tab in a path field completes against the local file system and moves on only when there is nothing to complete.</summary>
[TestClass]
public sealed class SettingsTuiPathCompletionTests : SettingsTuiTestBase
{
    private string _root = "";

    [TestInitialize]
    public void MakeTree()
    {
        _root = Path.Combine(Path.GetTempPath(), "tui-pathcompletion-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(Path.Combine(_root, "staging"));
        Directory.CreateDirectory(Path.Combine(_root, "state"));
        Directory.CreateDirectory(Path.Combine(_root, "reports"));
    }

    [TestCleanup]
    public void RemoveTree() => Directory.Delete(_root, true);

    private SettingsTuiHarness OnArchives()
    {
        var tui = Start();
        tui.Window.PageIndex = PageCatalog.Titles.ToList().IndexOf("Archives");
        tui.Press(Key.Enter);
        tui.TabTo("Staging Area");
        return tui;
    }

    [TestMethod]
    public void Tab_completes_a_unique_match_and_keeps_the_focus_in_the_field()
    {
        var tui = OnArchives();
        tui.Type(_root + "/rep");

        tui.Press(Key.Tab);

        Assert.AreEqual(_root + "/reports/", tui.FocusedText);
        Assert.AreEqual(_root + "/reports/", tui.Page.Field("Archive:StagingPath").Value);
        Assert.AreEqual("Staging Area", tui.FocusedFieldLabel);
    }

    [TestMethod]
    public void Tab_on_an_ambiguous_prefix_completes_the_common_part_and_lists_the_candidates()
    {
        var tui = OnArchives();
        tui.Type(_root + "/s");

        tui.Press(Key.Tab);

        Assert.AreEqual(_root + "/sta", tui.FocusedText);
        Assert.AreEqual("Staging Area", tui.FocusedFieldLabel);
        Assert.IsTrue(tui.Shows("staging/") && tui.Shows("state/"), tui.Screen);

        tui.Type("g");
        Assert.IsFalse(tui.Shows("state/"), "typing clears the candidate list");
    }

    [TestMethod]
    public void Tab_moves_to_the_next_field_when_there_is_nothing_to_complete()
    {
        var tui = OnArchives();
        tui.Type(_root + "/nothing-here");

        tui.Press(Key.Tab);

        Assert.AreNotEqual("Staging Area", tui.FocusedFieldLabel, tui.FocusPath);
        Assert.AreEqual(_root + "/nothing-here", tui.Page.Field("Archive:StagingPath").Value);
    }

    [TestMethod]
    public void Tab_in_an_empty_path_field_moves_on()
    {
        var tui = OnArchives();

        tui.Press(Key.Tab);

        Assert.AreNotEqual("Staging Area", tui.FocusedFieldLabel, tui.FocusPath);
    }

    [TestMethod]
    public void Down_Up_and_Shift_Tab_always_navigate_even_when_a_completion_exists()
    {
        var tui = OnArchives();
        tui.Type(_root + "/rep");

        tui.Press(Key.CursorDown);
        var next = tui.FocusedFieldLabel;
        Assert.AreNotEqual("Staging Area", next);
        Assert.AreEqual(_root + "/rep", tui.Page.Field("Archive:StagingPath").Value);

        tui.Press(Key.CursorUp);
        Assert.AreEqual("Staging Area", tui.FocusedFieldLabel);

        tui.Press(Key.Tab.WithShift);
        Assert.AreNotEqual("Staging Area", tui.FocusedFieldLabel);
        Assert.AreEqual(_root + "/rep", tui.Page.Field("Archive:StagingPath").Value);
    }

    [TestMethod]
    public void Tab_in_a_text_field_that_is_not_a_path_still_navigates()
    {
        var tui = Start();
        tui.Press(Key.Enter);
        tui.Type("x");

        tui.Press(Key.Tab);

        Assert.AreEqual("Port", tui.FocusedFieldLabel);
    }

    [TestMethod]
    public void The_Data_Directory_Report_and_Log_directory_fields_complete_too()
    {
        foreach (var (page, label) in new[] { ("Data Directory", "Data Directory"), ("Reports and logs", "Report directory"), ("Reports and logs", "Log directory") })
        {
            var tui = Start();
            tui.Window.PageIndex = PageCatalog.Titles.ToList().IndexOf(page);
            tui.Press(Key.Enter);
            tui.TabTo(label);
            tui.Type(_root + "/rep");

            tui.Press(Key.Tab);

            Assert.AreEqual(_root + "/reports/", tui.FocusedText, label);
        }
    }

    [TestMethod]
    public void A_Directory_Source_path_completes()
    {
        var tui = Start();
        tui.Window.PageIndex = PageCatalog.Titles.ToList().IndexOf("Sources");
        tui.Press(Key.Enter); // into the list
        tui.Press(Key.Tab);   // Add
        tui.Press(Key.Enter); // adds a Source and focuses its Name
        tui.Press(Key.Tab);   // Type
        tui.Press(Key.Tab);   // Enabled
        tui.Press(Key.Tab);   // Directory path
        Assert.IsInstanceOfType<TextField>(tui.Focused, tui.FocusPath);
        tui.Type(_root + "/rep");

        tui.Press(Key.Tab);

        Assert.AreEqual(_root + "/reports/", tui.FocusedText);
    }
}

using MiresSftpUploader.SettingsTui;
using Terminal.Gui.Input;
using Terminal.Gui.Views;

namespace MiresSftpUploader.Test.Unit;

/// <summary>The form pane and the in-place list updates, the parts later pages reuse.</summary>
[TestClass]
public sealed class SettingsTuiFormPaneTests : SettingsTuiTestBase
{
    private static FormPane PaneWith(SettingsTuiHarness tui, params (string Label, string[] Value)[] rows)
    {
        var pane = new FormPane(rows.Select(r => FormRows.TextRow(r.Label, () => r.Value[0], v => r.Value[0] = v)));
        foreach (var old in tui.Window.Body.SubViews.ToList()) { tui.Window.Body.Remove(old); old.Dispose(); }
        tui.Window.Body.Add(pane);
        tui.Draw();
        return pane;
    }

    [TestMethod]
    public void Plain_rows_are_bound_through_a_getter_and_setter_and_Tab_walks_them()
    {
        var tui = Start();
        var a = new[] { "one" };
        var b = new[] { "two" };
        var pane = PaneWith(tui, ("First", a), ("Second", b));

        Assert.IsTrue(pane.FocusFirstInput());
        tui.Type("X");
        tui.Press(Key.Tab);
        tui.Type("Y");

        Assert.AreEqual("X", a[0], "a focused text box has its text selected, so typing replaces it");
        Assert.AreEqual("Y", b[0]);
    }

    [TestMethod]
    public void ReplaceRows_swaps_the_rows_and_navigation_covers_the_new_ones()
    {
        var tui = Start();
        var pane = PaneWith(tui, ("First", new[] { "a" }));
        var c = new[] { "c" };
        var d = new[] { "d" };

        pane.ReplaceRows([FormRows.TextRow("Third", () => c[0], v => c[0] = v), FormRows.TextRow("Fourth", () => d[0], v => d[0] = v)]);
        tui.Draw();
        pane.FocusFirstInput();
        tui.Press(Key.Tab);
        tui.Type("Z");

        Assert.HasCount(2, pane.Rows);
        Assert.IsFalse(tui.Shows("First"));
        Assert.AreEqual("Z", d[0]);
    }

    [TestMethod]
    public void ListSync_updates_a_collection_in_place_without_replacing_it()
    {
        var items = new System.Collections.ObjectModel.ObservableCollection<string>(["a", "b", "c"]);
        var events = new List<System.Collections.Specialized.NotifyCollectionChangedAction>();
        items.CollectionChanged += (_, e) => events.Add(e.Action);

        ListSync.Update(items, ["a", "B", "c", "d"]);
        ListSync.Update(items, ["a"]);

        CollectionAssert.AreEqual(new[] { "a" }, items);
        Assert.DoesNotContain(System.Collections.Specialized.NotifyCollectionChangedAction.Reset, events, "never a reset: that is what drops focus");
    }

    [TestMethod]
    public void Typing_updates_the_sidebar_badge_in_place_and_does_not_replace_the_list_source()
    {
        var tui = Start();
        var source = tui.Window.Sidebar.Source;
        tui.Press(Key.Enter);
        tui.TabTo("Port");

        tui.Type("9");

        Assert.AreSame(source, tui.Window.Sidebar.Source);
        Assert.AreEqual("● Destination", tui.Window.Sidebar.Items[0]);
        Assert.AreEqual("Port", tui.FocusedFieldLabel);
    }
}

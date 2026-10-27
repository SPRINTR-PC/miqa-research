using System.Collections.Generic;
using System.Collections.ObjectModel;
using Terminal.Gui.Input;
using Terminal.Gui.ViewBase;
using Terminal.Gui.Views;

namespace MiresSftpUploader.SettingsTui;

/// <summary>
/// The focus levels of the Settings TUI: sidebar, then a page's form (or a master/detail page's list), then a master/detail page's detail form.
/// Enter or Right goes one level in, Esc one level out. Terminal.Gui's own Tab does not traverse nested containers, so this does it.
/// </summary>
public static class FocusLevels
{
    /// <summary>Moves focus to the first input (a leaf with a tab stop) under <paramref name="root"/>.</summary>
    public static bool FocusFirstInput(View root)
    {
        foreach (var v in root.SubViews)
        {
            if (v.CanFocus && v.TabStop == TabBehavior.TabStop && v.Enabled && v.Visible) { v.SetFocus(); return true; }
            if (FocusFirstInput(v)) return true;
        }

        return false;
    }

    /// <summary>Every input (focusable leaf with a tab stop, enabled and visible) under <paramref name="root"/>, in display order.</summary>
    public static List<View> Inputs(View root)
    {
        var into = new List<View>();
        Collect(root, into);
        return into;
    }

    private static void Collect(View root, List<View> into)
    {
        foreach (var v in root.SubViews)
        {
            if (v.CanFocus && v.TabStop == TabBehavior.TabStop && v.Enabled && v.Visible) into.Add(v);
            else Collect(v, into);
        }
    }

    /// <summary>
    /// Master/detail wiring: Enter or Right in <paramref name="list"/> enters <paramref name="detail"/>, and Esc inside the detail
    /// (see <see cref="Back"/>) returns to the list. The list is recorded in <c>detail.Data</c>.
    /// </summary>
    public static void Link(ListView list, View detail)
    {
        detail.Data = list;
        list.Accepting += (_, e) => { FocusFirstInput(detail); e.Handled = true; };
        list.KeyDown += (_, k) =>
        {
            if (k != Key.CursorRight) return;
            FocusFirstInput(detail);
            k.Handled = true;
        };
    }

    /// <summary>Esc: from inside a linked detail go back to its list, otherwise to <paramref name="fallback"/> (the sidebar).</summary>
    public static void Back(View scope, View fallback)
    {
        for (var v = scope.MostFocused; v is not null && v != scope; v = v.SuperView)
            if (v.Data is ListView list) { list.SetFocus(); return; }

        fallback.SetFocus();
    }
}

/// <summary>
/// Updates a <see cref="ListView"/>'s backing collection in place. Assigning a new <c>ListView.Source</c> steals focus and resets the selection
/// (this dropped the cursor while typing a Source name), so every list, and the sidebar badges, change through this.
/// </summary>
public static class ListSync
{
    public static void Update(ObservableCollection<string> target, IReadOnlyList<string> items)
    {
        for (var i = 0; i < items.Count; i++)
        {
            if (i < target.Count) { if (target[i] != items[i]) target[i] = items[i]; }
            else target.Add(items[i]);
        }

        while (target.Count > items.Count) target.RemoveAt(target.Count - 1);
    }
}

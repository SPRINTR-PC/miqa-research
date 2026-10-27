#pragma warning disable CS0618 // TextView: the multi-line box for Lines settings; its replacement is a separate package
using System;
using System.Collections.Generic;
using System.Linq;
using Terminal.Gui.Input;
using Terminal.Gui.ViewBase;
using Terminal.Gui.Views;

namespace MiresSftpUploader.SettingsTui;

/// <summary>
/// A vertical stack of rows that scrolls when it is taller than the pane and follows focus. It owns its field navigation: Terminal.Gui's Tab
/// skips inputs nested in row containers, so Tab/Down move to the next input and Shift+Tab/Up to the previous one, and at either end the key
/// falls through (to the sidebar for Shift+Tab/Up on the first input). Up/Down stay with multi-line boxes and dropdowns.
/// Tab in a <see cref="PathTextField"/> completes the path first and navigates only when there is nothing to complete.
/// Reusable by any page: pass it rows (see <see cref="FormRows"/>); a row is any view whose inputs are focusable leaves.
/// </summary>
public sealed class FormPane : View
{
    private readonly List<View> _rows = [];
    private int _height;

    public FormPane(IEnumerable<View> rows)
    {
        Width = Dim.Fill();
        Height = Dim.Fill();
        CanFocus = true;
        TabStop = TabBehavior.NoStop;
        ViewportSettings |= ViewportSettingsFlags.HasVerticalScrollBar;
        Layout(rows);
        FrameChanged += (_, _) => Fit();
        KeyDown += OnKey;
    }

    public IReadOnlyList<View> Rows => _rows;

    /// <summary>Replaces all rows (for a form that changes shape, such as a Source switching between Directory and S3). The old rows are disposed.</summary>
    public void ReplaceRows(IEnumerable<View> rows)
    {
        foreach (var old in _rows) { Remove(old); old.Dispose(); }
        _rows.Clear();
        Layout(rows);
    }

    /// <summary>Focuses the first enabled input; false when there is none (a read-only page).</summary>
    public bool FocusFirstInput() => FocusLevels.FocusFirstInput(this);

    private void Layout(IEnumerable<View> rows)
    {
        foreach (var row in rows)
        {
            row.Y = _rows.Count == 0 ? 0 : Pos.Bottom(_rows[^1]); // a row may size itself to its content, so rows stack on each other
            row.X = 0;
            row.Width = Dim.Fill(1);
            Add(row);
            _rows.Add(row);
            var captured = row;
            row.FrameChanged += (_, _) => Fit();
            row.HasFocusChanged += (_, e) => { if (e.NewValue) Ensure(captured); };
        }

        Fit();
    }

    private void OnKey(object? sender, Key k)
    {
        if (k == Key.Tab && MostFocused is PathTextField path && path.TryComplete())
        {
            k.Handled = true;
            return;
        }

        var dir = k == Key.Tab || k == Key.CursorDown ? 1 : k == Key.Tab.WithShift || k == Key.CursorUp ? -1 : 0;
        if (dir == 0) return;
        var focused = MostFocused;
        if (focused is TextView or DropDownList or ListView && (k == Key.CursorDown || k == Key.CursorUp)) return;
        var inputs = new List<View>();
        Collect(this, inputs);
        var at = inputs.IndexOf(focused!);
        var next = at + dir;
        if (at < 0 || next < 0 || next >= inputs.Count) return;
        inputs[next].SetFocus();
        k.Handled = true;
    }

    private static void Collect(View root, List<View> into)
    {
        foreach (var v in root.SubViews)
        {
            if (v.CanFocus && v.TabStop == TabBehavior.TabStop && v.Enabled && v.Visible) into.Add(v);
            else Collect(v, into);
        }
    }

    private void Fit()
    {
        _height = _rows.Count == 0 ? 0 : _rows.Max(r => r.Frame.Bottom);
        var size = new System.Drawing.Size(Math.Max(1, Viewport.Width), _height);
        if (GetContentSize() != size) SetContentSize(size);
    }

    private void Ensure(View row)
    {
        var top = row.Frame.Y;
        var bottom = row.Frame.Bottom;
        if (top < Viewport.Y) ScrollVertical(top - Viewport.Y);
        else if (bottom > Viewport.Y + Viewport.Height) ScrollVertical(bottom - (Viewport.Y + Viewport.Height));
    }
}

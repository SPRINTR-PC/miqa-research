using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Linq;
using MiresSftpUploader.ViewModels;
using Terminal.Gui.ViewBase;
using Terminal.Gui.Views;

namespace MiresSftpUploader.SettingsTui;

/// <summary>
/// The row kinds a <see cref="FormPane"/> is built from. <see cref="Field"/> / <see cref="ForGroup"/> are the full row for a
/// <see cref="SettingFieldViewModel"/> (changed marker, inline error, lock reason, help). The plain rows (<see cref="TextRow"/>,
/// <see cref="ChoiceRow"/>, <see cref="ToggleRow"/>) bind to any property through a getter and setter, for view models that are not fields
/// (a Source, an Archive Rule). Every row is one line (a Field row is two) with its label at column 0 and its input at <see cref="LabelWidth"/> + 1.
/// </summary>
public static class FormRows
{
    public const int LabelWidth = 34;

    public static string Fit(string s, int width) => s.Length <= width ? s.PadRight(width) : s[..(width - 1)] + "…";

    public static ListWrapper<string> Items(IEnumerable<string> items) => new(new ObservableCollection<string>(items));

    public static FieldRow Field(SettingFieldViewModel field) => new(field);

    public static IEnumerable<View> ForGroup(SettingsPageViewModel vm, string group) =>
        vm.Fields.Where(f => f.Group == group).Select(f => (View)new FieldRow(f));

    public static Label Note(string text) => new Label { Width = Dim.Fill(), Text = text }.Apply(Theme.Help);

    public static Button Btn(string text, Action action)
    {
        var b = new Button { Text = text };
        b.Accepting += (_, e) => { action(); e.Handled = true; };
        return b;
    }

    private static View Row() => new() { Width = Dim.Fill(), Height = 1, CanFocus = true, TabStop = TabBehavior.NoStop };

    public static View TextRow(string label, Func<string> get, Action<string> set, bool enabled = true, bool secret = false)
    {
        var row = Row();
        var tf = new TextField { X = LabelWidth + 1, Width = Dim.Fill(1), Text = get(), Enabled = enabled, Secret = secret };
        tf.TextChanged += (_, _) => { if (tf.Text != get()) set(tf.Text); };
        row.Add(new Label { Text = Fit(label, LabelWidth) }, tf);
        return row;
    }

    /// <summary>A text row for a local path: Tab completes it, and the candidates of an ambiguous completion show on a second line.</summary>
    public static View PathRow(string label, Func<string> get, Action<string> set, bool enabled = true)
    {
        var row = new View { Width = Dim.Fill(), Height = 2, CanFocus = true, TabStop = TabBehavior.NoStop };
        var tf = new PathTextField { X = LabelWidth + 1, Width = Dim.Fill(1), Text = get(), Enabled = enabled };
        tf.TextChanged += (_, _) => { if (tf.Text != get()) set(tf.Text); };
        var candidates = new Label { X = LabelWidth + 1, Y = 1, Width = Dim.Fill(1) }.Apply(Theme.Help);
        tf.CandidatesChanged += (_, _) => candidates.Text = string.Join("  ", tf.Candidates);
        row.Add(new Label { Text = Fit(label, LabelWidth) }, tf, candidates);
        return row;
    }

    public static View ChoiceRow(string label, IEnumerable<string> options, Func<string> get, Action<string> set, bool enabled = true)
    {
        var row = Row();
        var dd = new DropDownList { X = LabelWidth + 1, Width = 20, Source = Items(options), ReadOnly = true, Value = get(), Enabled = enabled };
        dd.ValueChanged += (_, e) => { if (e.NewValue is string s && s != get()) set(s); };
        row.Add(new Label { Text = Fit(label, LabelWidth) }, dd);
        return row;
    }

    public static View ToggleRow(string label, Func<bool> get, Action<bool> set, bool enabled = true)
    {
        var row = Row();
        var cb = new CheckBox { X = LabelWidth + 1, Text = "on", Value = get() ? CheckState.Checked : CheckState.UnChecked, Enabled = enabled };
        cb.ValueChanged += (_, _) => set(cb.Value == CheckState.Checked);
        row.Add(new Label { Text = Fit(label, LabelWidth) }, cb);
        return row;
    }
}

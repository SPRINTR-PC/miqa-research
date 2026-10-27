#pragma warning disable CS0618 // TextView: the multi-line box for Lines settings; its replacement is a separate package
using System;
using System.ComponentModel;
using MiresSftpUploader.ViewModels;
using Terminal.Gui.ViewBase;
using Terminal.Gui.Views;

namespace MiresSftpUploader.SettingsTui;

/// <summary>
/// One setting of the Settings page: label with a changed marker (<c>●</c>), the input for its kind (text, number and path as a text box,
/// toggle, choice, lines as a multi-line box), and a second line for the inline error (<c>✗</c>), the lock reason (<c>🔒</c>), a note or the help text.
/// The Host Key Fingerprint gets an Unlock button. Typing writes to the view model at once; the view model's changes redraw the row.
/// </summary>
public sealed class FieldRow : View
{
    private readonly Label _label = new();
    private readonly Label _meta = new();
    private readonly View _input;
    private readonly Button? _unlock;

    public FieldRow(SettingFieldViewModel field)
    {
        Field = field;
        Width = Dim.Fill();
        CanFocus = true;
        TabStop = TabBehavior.NoStop;
        var lines = field.IsLines;
        Height = lines ? 6 : 2;
        _label.X = 0;
        _label.Y = 0;
        Add(_label);
        _meta.X = lines ? 2 : FormRows.LabelWidth + 1;
        _meta.Y = lines ? 5 : 1;
        _meta.Width = Dim.Fill();
        Add(_meta);
        SetScheme(Theme.Pane);

        switch (field.Kind)
        {
            case FieldKind.Toggle:
            {
                var cb = new CheckBox { X = FormRows.LabelWidth + 1, Text = "on", Value = field.BoolValue ? CheckState.Checked : CheckState.UnChecked };
                cb.ValueChanged += (_, _) => field.BoolValue = cb.Value == CheckState.Checked;
                _input = cb;
                break;
            }
            case FieldKind.Choice:
            {
                var dd = new DropDownList { X = FormRows.LabelWidth + 1, Width = 20, Source = FormRows.Items(field.Options), ReadOnly = true, Value = field.Value };
                dd.ValueChanged += (_, e) => { if (e.NewValue is string s && s != field.Value) field.Value = s; };
                _input = dd;
                break;
            }
            case FieldKind.Lines:
            {
                _label.Width = Dim.Fill();
                var tv = new TextView { X = 2, Y = 1, Width = Dim.Fill(2), Height = 4, Text = field.Value, TabKeyAddsTab = false }; // Tab leaves the box (a Tab character is never wanted in a path or pattern)
                tv.ContentsChanged += (_, _) => // TextChanged only fires for programmatic changes; ContentsChanged for typing
 { if (tv.Text != field.Value) field.Value = tv.Text; };
                _input = tv;
                break;
            }
            default:
            {
                var tf = field.Kind == FieldKind.Path ? new PathTextField() : new TextField();
                tf.X = FormRows.LabelWidth + 1;
                tf.Width = field.NeedsUnlock ? Dim.Fill(12) : Dim.Fill(1);
                tf.Text = field.Value;
                if (tf is PathTextField pt) pt.CandidatesChanged += (_, _) => Refresh();
                tf.TextChanged += (_, _) => { if (tf.Text != field.Value) field.Value = tf.Text; };
                _input = tf;
                if (field.NeedsUnlock)
                {
                    _unlock = FormRows.Btn("Unlock", () => field.UnlockCommand?.Fire(this));
                    _unlock.X = Pos.AnchorEnd(10);
                    _unlock.Y = 0;
                    Add(_unlock);
                }

                break;
            }
        }

        Add(_input);
        field.PropertyChanged += OnChanged;
        Refresh();
    }

    public SettingFieldViewModel Field { get; }

    /// <summary>The text box, drop-down, check box or multi-line box.</summary>
    public View Input => _input;

    private void OnChanged(object? s, PropertyChangedEventArgs e) => Refresh();

    private void Refresh()
    {
        var f = Field;
        _label.Text = (f.IsChanged ? "● " : "  ") + (f.IsLines ? f.Label : FormRows.Fit(f.Label, FormRows.LabelWidth - 2));
        _input.Enabled = f.IsEditable;
        _label.SetScheme(f.HasError ? Theme.Error : f.IsChanged ? Theme.Changed : f.IsEditable ? Theme.Pane : Theme.Locked);
        _meta.SetScheme(f.HasError ? Theme.Error : f.HasLockReason || f.HasUnlockButton ? Theme.Locked : f.Note is not null ? Theme.Pane : Theme.Help);
        if (_unlock is not null) _unlock.Visible = f.HasUnlockButton;
        _meta.Text = f.HasError ? "✗ " + f.Error
            : f.HasLockReason ? "🔒 " + f.LockReason
            : f.HasUnlockButton ? "locked until you press Unlock"
            : _input is PathTextField { Candidates.Count: > 0 } p ? string.Join("  ", p.Candidates)
            : f.Note ?? f.Help ?? "";
        SetNeedsDraw();
    }

    protected override void Dispose(bool disposing)
    {
        if (disposing) Field.PropertyChanged -= OnChanged;
        base.Dispose(disposing);
    }
}

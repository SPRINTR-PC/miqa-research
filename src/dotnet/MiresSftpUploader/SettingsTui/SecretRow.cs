using System;
using System.ComponentModel;
using MiresSftpUploader.Core;
using MiresSftpUploader.ViewModels;
using Terminal.Gui.ViewBase;
using Terminal.Gui.Views;

namespace MiresSftpUploader.SettingsTui;

/// <summary>
/// One Secret, four lines so that it fits the narrow form of a Source: label and masked field; the status (set, not set, set by an
/// environment variable) under the label with Save and Clear beside it; and, in two wrapping lines, why the row is disabled or what went wrong.
/// Drives a <see cref="SecretEntryViewModel"/> unchanged. Enter in the field means Save, Clear asks nothing, and both act on the Secret Store at
/// once, independent of the page Save. The value typed lives only in the masked field and the view model's Input until Save hands it to the
/// store; it is never drawn or logged.
/// </summary>
public sealed class SecretRow : View
{
    public const int RowHeight = 4;

    private readonly SecretEntryViewModel _entry;
    private readonly TextField _field;
    private readonly Button _save;
    private readonly Button _clear;
    private readonly Label _status = new() { X = 2, Y = 1, Width = FormRows.LabelWidth - 2 };
    private readonly Label _detail = new() { X = 2, Y = 2, Width = Dim.Fill(1), Height = 2 };

    public SecretRow(SecretEntryViewModel entry)
    {
        _entry = entry;
        Width = Dim.Fill();
        Height = RowHeight;
        CanFocus = true;
        TabStop = TabBehavior.NoStop;
        SetScheme(Theme.Pane);

        _field = new TextField { X = FormRows.LabelWidth + 1, Width = Dim.Fill(1), Secret = true };
        _field.TextChanged += (_, _) => { if (_field.Text != entry.Input) entry.Input = _field.Text; };
        _field.Accepting += (_, e) => { Save(); e.Handled = true; };
        _save = FormRows.Btn("Save", Save);
        _save.X = FormRows.LabelWidth + 1;
        _save.Y = 1;
        _clear = FormRows.Btn("Clear", Clear);
        _clear.X = FormRows.LabelWidth + 11;
        _clear.Y = 1;
        Add(new Label { Text = FormRows.Fit(entry.Label, FormRows.LabelWidth) }, _field, _status, _save, _clear, _detail);

        entry.PropertyChanged += OnChanged;
        Refresh();
    }

    public SecretEntryViewModel Entry => _entry;

    // ReactiveCommand.Execute() does not look at CanExecute, so the guard is here: Enter in an empty field must not store an empty Secret.
    private bool CanSave => !_entry.IsLocked && _entry.StoreAvailable && _entry.Input.Length > 0;

    private void Save()
    {
        if (CanSave) _entry.SaveCommand.Fire(this);
    }

    private void Clear()
    {
        if (_entry.CanClear) _entry.ClearCommand.Fire(this);
    }

    private void OnChanged(object? s, PropertyChangedEventArgs e) => Refresh();

    /// <summary>The status as the row shows it. Never a value.</summary>
    public static string StatusText(SecretEntryViewModel e) => e.Origin switch
    {
        SecretOrigin.Environment => "set by an environment variable",
        SecretOrigin.Stored => "set",
        SecretOrigin.Unreadable => "unreadable",
        _ => "not set",
    };

    private void Refresh()
    {
        var e = _entry;
        if (_field.Text != e.Input) _field.Text = e.Input;
        _field.Enabled = !e.IsLocked && e.StoreAvailable;
        _save.Enabled = CanSave;
        _clear.Enabled = e.CanClear;
        _status.Text = StatusText(e);
        _status.SetScheme(e.IsLocked || !e.StoreAvailable ? Theme.Locked : e.Origin == SecretOrigin.NotSet ? Theme.Help : Theme.Changed);
        if (e.Error.Length > 0)
        {
            _detail.Text = "✗ " + e.Error;
            _detail.SetScheme(Theme.Error);
        }
        else
        {
            _detail.Text = !e.StoreAvailable ? "🔒 " + e.StoreProblem
                : e.IsLocked ? "🔒 Supplied by an environment variable, which wins; unset it to change it here."
                : e.Origin == SecretOrigin.Unreadable ? "! " + e.Status
                : "";
            _detail.SetScheme(Theme.Locked);
        }

        SetNeedsDraw();
    }

    protected override void Dispose(bool disposing)
    {
        if (disposing) _entry.PropertyChanged -= OnChanged;
        base.Dispose(disposing);
    }
}

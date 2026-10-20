using System;
using System.Collections.Generic;
using MiresSftpUploader.Core;
using ReactiveUI;

namespace MiresSftpUploader.ViewModels;

public enum FieldKind { Text, Number, Toggle, Choice, Lines, Path }

/// <summary>One scalar (or plain list) setting on the Settings page: its edited text, whether it is a Locked Setting, and its inline error.</summary>
public sealed class SettingFieldViewModel : ViewModelBase
{
    private string _value;
    private string? _error;
    private bool _unlocked;
    private string? _note;

    public SettingFieldViewModel(string key, string label, string group, FieldKind kind, string original, SettingInfo info,
        IReadOnlyList<string>? options = null, string? help = null, bool needsUnlock = false)
    {
        Key = key;
        Label = label;
        Group = group;
        Kind = kind;
        Options = options ?? [];
        Help = help;
        Original = original;
        _value = original;
        NeedsUnlock = needsUnlock;
        IsLocked = info.Locked;
        LockReason = info.Locked ? Describe(info.Layer) : null;
    }

    public string Key { get; }
    public string Label { get; }
    public string Group { get; }
    public FieldKind Kind { get; }
    public IReadOnlyList<string> Options { get; }
    public string? Help { get; }
    public string Original { get; }

    /// <summary>The Host Key Fingerprint: read-only until the user confirms that they want to change it.</summary>
    public bool NeedsUnlock { get; }

    public bool IsLocked { get; }
    public string? LockReason { get; }

    public string Value
    {
        get => _value;
        set
        {
            if (_value == value) return;
            this.RaiseAndSetIfChanged(ref _value, value);
            this.RaisePropertyChanged(nameof(IsChanged));
            this.RaisePropertyChanged(nameof(BoolValue));
            ValueChanged?.Invoke();
        }
    }

    internal event Action? ValueChanged;

    public bool BoolValue
    {
        get => string.Equals(_value, "true", StringComparison.OrdinalIgnoreCase);
        set => Value = value ? "true" : "false";
    }

    public bool IsChanged => _value != Original;
    public bool IsEditable => !IsLocked && (!NeedsUnlock || _unlocked);
    public bool IsText => Kind is FieldKind.Text or FieldKind.Number or FieldKind.Path;
    public bool IsToggle => Kind == FieldKind.Toggle;
    public bool IsChoice => Kind == FieldKind.Choice;
    public bool IsLines => Kind == FieldKind.Lines;
    public bool HasBrowse => Kind == FieldKind.Path;
    public bool HasLockReason => LockReason is not null;

    public void Unlock()
    {
        _unlocked = true;
        this.RaisePropertyChanged(nameof(IsEditable));
    }

    public string? Error
    {
        get => _error;
        set
        {
            this.RaiseAndSetIfChanged(ref _error, value);
            this.RaisePropertyChanged(nameof(HasError));
        }
    }

    public bool HasError => _error is not null;

    /// <summary>A hint shown under the field that depends on its value, such as the cost of a Verification level.</summary>
    public string? Note
    {
        get => _note;
        set
        {
            this.RaiseAndSetIfChanged(ref _note, value);
            this.RaisePropertyChanged(nameof(HasNote));
        }
    }

    public bool HasNote => _note is not null;

    private static string Describe(ConfigLayer layer) => layer switch
    {
        ConfigLayer.Environment => "Set by an environment variable (MIRES_*); change it there.",
        ConfigLayer.Cli => "Set by a command-line flag.",
        _ => "Set in Machine Config, which this account cannot write; an administrator changes it.",
    };
}

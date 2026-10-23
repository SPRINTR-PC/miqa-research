using System;
using System.Reactive;
using MiresSftpUploader.Core;
using ReactiveUI;

namespace MiresSftpUploader.ViewModels;

/// <summary>
/// One Secret on the Settings page: where it comes from, a masked box to type a new value, and Save and Clear. The value
/// typed is handed to the Secret Store and dropped; nothing ever reads a stored value back into the screen.
/// </summary>
public sealed class SecretEntryViewModel : ViewModelBase
{
    private readonly Func<string, string, string?> _set;
    private readonly Func<string, string?> _clear;
    private readonly Action _changed;
    private SecretOrigin _origin;
    private string? _storeProblem;
    private string _input = "";
    private string _error = "";

    public SecretEntryViewModel(string name, string label, Func<string, string, string?> set, Func<string, string?> clear, Action changed)
    {
        Name = name;
        Label = label;
        _set = set;
        _clear = clear;
        _changed = changed;
        SaveCommand = ReactiveCommand.Create(Save, this.WhenAnyValue(x => x.Input, x => x.IsLocked, x => x.StoreAvailable,
            (input, locked, available) => input.Length > 0 && !locked && available));
        ClearCommand = ReactiveCommand.Create(Clear, this.WhenAnyValue(x => x.CanClear));
    }

    /// <summary>The Secret Store name, such as <c>sftp-password</c>.</summary>
    public string Name { get; }
    public string Label { get; }

    public ReactiveCommand<Unit, Unit> SaveCommand { get; }
    public ReactiveCommand<Unit, Unit> ClearCommand { get; }

    /// <summary>What the user is typing. Cleared after a successful Save.</summary>
    public string Input { get => _input; set => this.RaiseAndSetIfChanged(ref _input, value); }

    public string Error { get => _error; private set => this.RaiseAndSetIfChanged(ref _error, value); }

    public SecretOrigin Origin => _origin;

    public string Status => _origin switch
    {
        SecretOrigin.Environment => "environment variable",
        SecretOrigin.Stored => "stored",
        SecretOrigin.Unreadable => "unreadable on this machine, re-enter it",
        _ => "not set",
    };

    /// <summary>Supplied by an environment variable, which wins: the box is disabled.</summary>
    public bool IsLocked => _origin == SecretOrigin.Environment;

    public bool StoreAvailable => _storeProblem is null;

    /// <summary>Why the Secret Store cannot be used, or empty.</summary>
    public string StoreProblem => _storeProblem ?? "";

    public bool CanClear => _origin is SecretOrigin.Stored or SecretOrigin.Unreadable;

    internal void Refresh(SecretOrigin origin, string? storeProblem)
    {
        _origin = origin;
        _storeProblem = storeProblem;
        this.RaisePropertyChanged(nameof(Origin));
        this.RaisePropertyChanged(nameof(Status));
        this.RaisePropertyChanged(nameof(IsLocked));
        this.RaisePropertyChanged(nameof(StoreAvailable));
        this.RaisePropertyChanged(nameof(StoreProblem));
        this.RaisePropertyChanged(nameof(CanClear));
    }

    private void Save()
    {
        var problem = _set(Name, Input);
        Error = problem ?? "";
        if (problem is null) Input = "";
        _changed();
    }

    private void Clear()
    {
        Error = _clear(Name) ?? "";
        _changed();
    }
}

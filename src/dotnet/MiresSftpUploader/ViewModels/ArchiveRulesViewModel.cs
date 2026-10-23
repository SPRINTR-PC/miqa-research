using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Linq;
using System.Reactive;
using System.Reactive.Linq;
using ReactiveUI;

namespace MiresSftpUploader.ViewModels;

/// <summary>The editable list of Archive Rules of one scope: the global rules or one Source's own.</summary>
public sealed class ArchiveRulesViewModel : ViewModelBase
{
    private readonly string _original;
    private string _error = "";

    internal ArchiveRulesViewModel(IEnumerable<IReadOnlyDictionary<string, string>> entries, bool locked)
    {
        IsLocked = locked;
        foreach (var entry in entries) Attach(new ArchiveRuleEditorViewModel(entry));
        _original = Snapshot();
        AddRuleCommand = ReactiveCommand.Create(() =>
        {
            Attach(ArchiveRuleEditorViewModel.Blank());
            Changed();
        }, Observable.Return(!locked));
        RemoveRuleCommand = ReactiveCommand.Create<ArchiveRuleEditorViewModel>(rule =>
        {
            Rules.Remove(rule);
            Changed();
        }, Observable.Return(!locked));
    }

    public ObservableCollection<ArchiveRuleEditorViewModel> Rules { get; } = [];
    public ReactiveCommand<Unit, Unit> AddRuleCommand { get; }
    public ReactiveCommand<ArchiveRuleEditorViewModel, Unit> RemoveRuleCommand { get; }

    public bool IsLocked { get; }
    public bool IsEditable => !IsLocked;
    public bool IsChanged => !IsLocked && Snapshot() != _original;
    public bool IsEmpty => Rules.Count == 0;

    public string Error { get => _error; internal set { this.RaiseAndSetIfChanged(ref _error, value); this.RaisePropertyChanged(nameof(HasError)); } }
    public bool HasError => _error.Length > 0;

    internal event Action? Edited;

    /// <summary>The flat keys of the rules under <paramref name="prefix"/> (<c>Archive:Rules</c>, <c>ArchiveRules</c>), numbered in list order.</summary>
    internal IEnumerable<KeyValuePair<string, string>> ToFlat(string prefix) =>
        Rules.SelectMany((rule, i) => rule.ToEntry().Select(kv => KeyValuePair.Create($"{prefix}:{i}:{kv.Key}", kv.Value)));

    private void Attach(ArchiveRuleEditorViewModel rule)
    {
        rule.Edited += Changed;
        Rules.Add(rule);
    }

    private void Changed()
    {
        this.RaisePropertyChanged(nameof(IsChanged));
        this.RaisePropertyChanged(nameof(IsEmpty));
        Edited?.Invoke();
    }

    private string Snapshot() => string.Join("\n", ToFlat("r").Select(kv => $"{kv.Key}={kv.Value}"));
}

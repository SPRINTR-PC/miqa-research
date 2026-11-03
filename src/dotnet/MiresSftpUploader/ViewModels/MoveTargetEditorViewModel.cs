using System;
using System.Collections.Generic;
using System.Linq;
using System.Reactive;
using System.Threading.Tasks;
using ReactiveUI;

namespace MiresSftpUploader.ViewModels;

/// <summary>
/// One Post-upload Move of a Source being edited: where its files go once they were uploaded (OnSuccess) or finally failed (OnFailure).
/// A Directory Source moves them to a directory; an S3 Source to a bucket and prefix. Off means the files stay where they are.
/// </summary>
public sealed class MoveTargetEditorViewModel : ViewModelBase
{
    private readonly string _key;
    private readonly Action<string> _edited;
    private bool _move;
    private string _path = "";
    private string _bucket = "";
    private string _prefix = "";

    internal MoveTargetEditorViewModel(string key, string label, IReadOnlyDictionary<string, string> entry, Func<Task<string?>> pickFolder, Action<string> edited)
    {
        _key = key;
        _edited = edited;
        Label = label;
        string Get(string name) => entry.TryGetValue($"{key}:{name}", out var v) ? v : "";
        _move = string.Equals(Get("Action"), "Move", StringComparison.OrdinalIgnoreCase);
        _path = Get("Path");
        _bucket = Get("Bucket");
        _prefix = Get("Prefix");
        BrowseCommand = ReactiveCommand.CreateFromTask(async () =>
        {
            if (await pickFolder() is { } picked) Path = picked;
        });
    }

    /// <summary>The keys of a Source this editor owns, relative to the Source.</summary>
    internal static IEnumerable<string> KeysOf(string key) => new[] { "Action", "Path", "Bucket", "Prefix" }.Select(n => $"{key}:{n}");

    /// <summary>"Successfully uploaded files" or "Failed files": what the settings of this target are about.</summary>
    public string Label { get; }

    public ReactiveCommand<Unit, Unit> BrowseCommand { get; }

    public bool Move { get => _move; set => Set(ref _move, value, nameof(Move)); }
    public string Path { get => _path; set => Set(ref _path, value, nameof(Path)); }
    public string Bucket { get => _bucket; set => Set(ref _bucket, value, nameof(Bucket)); }
    public string Prefix { get => _prefix; set => Set(ref _prefix, value, nameof(Prefix)); }

    /// <summary>Adds this target's keys to the Source's entry: nothing at all while Move is off.</summary>
    internal void Write(Dictionary<string, string> entry, bool directory)
    {
        if (!Move) return;
        entry[$"{_key}:Action"] = "Move";
        void Put(string name, string value) { if (value.Trim().Length > 0) entry[$"{_key}:{name}"] = value.Trim(); }
        if (directory) Put("Path", Path);
        else
        {
            Put("Bucket", Bucket);
            Put("Prefix", Prefix);
        }
    }

    private void Set<T>(ref T field, T value, string property)
    {
        if (EqualityComparer<T>.Default.Equals(field, value)) return;
        this.RaiseAndSetIfChanged(ref field, value, property);
        _edited(property);
    }
}

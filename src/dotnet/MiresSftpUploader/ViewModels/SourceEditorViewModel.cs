using System;
using System.Collections.Generic;
using System.Linq;
using System.Reactive;
using System.Runtime.CompilerServices;
using System.Threading.Tasks;
using MiresSftpUploader.Core;
using ReactiveUI;

namespace MiresSftpUploader.ViewModels;

/// <summary>
/// One Source being edited on the Settings page. The fields adapt to <see cref="Type"/>; the settings the page does not edit
/// (Ignore Rules, Archive Rules, Post-upload Move, scan limits) travel in <see cref="Extras"/> and are saved back unchanged.
/// </summary>
public sealed class SourceEditorViewModel : ViewModelBase
{
    /// <summary>The keys of a Source the editor owns; everything else is kept as it was.</summary>
    internal static readonly string[] ManagedKeys =
        ["Name", "Type", "Enabled", "RemotePath", "Path", "Endpoint", "Bucket", "Prefix", "Region", "ForcePathStyle"];

    private string _name = "";
    private SourceType _type;
    private bool _enabled = true;
    private string _remotePath = "";
    private string _path = "";
    private string _endpoint = "";
    private string _bucket = "";
    private string _prefix = "";
    private string _region = "";
    private bool _forcePathStyle;
    private string _error = "";
    private string _warning = "";
    private string _secretStatus = "";

    internal SourceEditorViewModel(IReadOnlyDictionary<string, string> entry, bool locked, Func<Task<string?>> pickFolder, Func<string> remoteRoot)
    {
        Extras = entry.Where(kv => !IsManaged(kv.Key)).ToDictionary(kv => kv.Key, kv => kv.Value, StringComparer.OrdinalIgnoreCase);
        IsLocked = locked;
        _remoteRootAccessor = remoteRoot;
        string Get(string key) => entry.TryGetValue(key, out var v) ? v : "";
        _name = Get("Name");
        _type = Enum.TryParse<SourceType>(Get("Type"), true, out var t) ? t : SourceType.Directory;
        _enabled = !entry.TryGetValue("Enabled", out var enabled) || !string.Equals(enabled, "false", StringComparison.OrdinalIgnoreCase);
        _remotePath = Get("RemotePath");
        _path = Get("Path");
        _endpoint = Get("Endpoint");
        _bucket = Get("Bucket");
        _prefix = Get("Prefix");
        _region = Get("Region");
        _forcePathStyle = string.Equals(Get("ForcePathStyle"), "true", StringComparison.OrdinalIgnoreCase);
        Original = Snapshot();
        BrowseCommand = ReactiveCommand.CreateFromTask(async () =>
        {
            if (await pickFolder() is { } picked) Path = picked;
        });
    }

    /// <summary>A new, empty Directory Source.</summary>
    internal static SourceEditorViewModel Blank(Func<Task<string?>> pickFolder, Func<string> remoteRoot) =>
        new(new Dictionary<string, string> { ["Type"] = "Directory" }, locked: false, pickFolder, remoteRoot) { Original = "" };

    private readonly Func<string> _remoteRootAccessor;

    internal IReadOnlyDictionary<string, string> Extras { get; }
    internal string Original { get; private set; }
    internal event Action? Edited;

    public bool IsLocked { get; }
    public bool IsEditable => !IsLocked;
    public bool IsChanged => Snapshot() != Original;

    public ReactiveCommand<Unit, Unit> BrowseCommand { get; }

    public string Name { get => _name; set => Set(ref _name, value, [nameof(RemotePathPlaceholder)]); }
    public string RemotePath { get => _remotePath; set => Set(ref _remotePath, value); }
    public string Path { get => _path; set => Set(ref _path, value); }
    public string Endpoint { get => _endpoint; set => Set(ref _endpoint, value); }
    public string Bucket { get => _bucket; set => Set(ref _bucket, value); }
    public string Prefix { get => _prefix; set => Set(ref _prefix, value); }
    public string Region { get => _region; set => Set(ref _region, value); }
    public bool ForcePathStyle { get => _forcePathStyle; set => Set(ref _forcePathStyle, value); }
    public bool Enabled { get => _enabled; set => Set(ref _enabled, value); }

    public SourceType Type
    {
        get => _type;
        set
        {
            if (_type == value) return;
            Set(ref _type, value, [nameof(IsDirectory), nameof(IsS3), nameof(TypeName)]);
        }
    }

    /// <summary>The Type as the combo box shows it (<c>Directory</c> or <c>S3</c>).</summary>
    public string TypeName
    {
        get => Type.ToString();
        set => Type = Enum.Parse<SourceType>(value);
    }

    public bool IsDirectory => Type == SourceType.Directory;
    public bool IsS3 => Type == SourceType.S3;

    /// <summary>The Remote Path used when none is given: the Destination's remote root plus the Source name.</summary>
    public string RemotePathPlaceholder
    {
        get
        {
            var root = _remoteRootAccessor().TrimEnd('/');
            return $"{root}/{(Name.Length == 0 ? "<name>" : Name)}";
        }
    }

    public string Error { get => _error; internal set { this.RaiseAndSetIfChanged(ref _error, value); this.RaisePropertyChanged(nameof(HasError)); } }
    public bool HasError => _error.Length > 0;
    public string Warning { get => _warning; internal set { this.RaiseAndSetIfChanged(ref _warning, value); this.RaisePropertyChanged(nameof(HasWarning)); } }
    public bool HasWarning => _warning.Length > 0;

    /// <summary>For an S3 Source: whether its access and secret keys are set in the environment. Never their values.</summary>
    public string SecretStatus { get => _secretStatus; internal set => this.RaiseAndSetIfChanged(ref _secretStatus, value); }

    internal void RefreshPlaceholder() => this.RaisePropertyChanged(nameof(RemotePathPlaceholder));

    /// <summary>The keys relative to the Source: the ones the editor owns (only those that apply to the Type) plus the untouched extras.</summary>
    internal Dictionary<string, string> ToEntry()
    {
        var entry = new Dictionary<string, string>(Extras, StringComparer.OrdinalIgnoreCase)
        {
            ["Name"] = Name.Trim(),
            ["Type"] = Type.ToString(),
            ["Enabled"] = Enabled ? "true" : "false",
        };
        void Put(string key, string value) { if (value.Trim().Length > 0) entry[key] = value.Trim(); }
        Put("RemotePath", RemotePath);
        if (IsDirectory) Put("Path", Path);
        else
        {
            Put("Endpoint", Endpoint);
            Put("Bucket", Bucket);
            Put("Prefix", Prefix);
            Put("Region", Region);
            if (ForcePathStyle) entry["ForcePathStyle"] = "true";
        }
        return entry;
    }

    private string Snapshot()
    {
        var entry = ToEntry();
        return string.Join("\n", entry.OrderBy(kv => kv.Key, StringComparer.Ordinal).Select(kv => $"{kv.Key}={kv.Value}"));
    }

    private static bool IsManaged(string key) => Array.Exists(ManagedKeys, k => k.Equals(key, StringComparison.OrdinalIgnoreCase));

    private void Set<T>(ref T field, T value, string[]? alsoRaise = null, [CallerMemberName] string? property = null)
    {
        if (EqualityComparer<T>.Default.Equals(field, value)) return;
        this.RaiseAndSetIfChanged(ref field, value, property);
        foreach (var name in alsoRaise ?? []) this.RaisePropertyChanged(name);
        this.RaisePropertyChanged(nameof(IsChanged));
        Edited?.Invoke();
    }
}

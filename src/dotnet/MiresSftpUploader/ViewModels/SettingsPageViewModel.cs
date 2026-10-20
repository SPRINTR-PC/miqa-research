using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Linq;
using System.Reactive;
using System.Threading.Tasks;
using MiresSftpUploader.Core;
using ReactiveUI;

namespace MiresSftpUploader.ViewModels;

/// <summary>
/// The Settings page: every setting except Secrets, grouped. Locked Settings are shown but not editable; each edit is
/// validated by <see cref="Configuration.Check"/> and an error disables Save. Save writes User Overrides.
/// </summary>
public sealed class SettingsPageViewModel : ViewModelBase
{
    private const string FingerprintKey = "Sftp:HostKeyFingerprint";
    private static readonly string[] Levels = ["Off", "Size", "Hash", "ReadBack"];
    private static readonly string[] LogLevels = ["Trace", "Debug", "Info", "Warn", "Error", "Fatal"];

    // Upload:VerifyCommand and State:AccessGroup are deliberately absent: they are Machine Config or environment only.
    private static readonly (string Key, string Label, string Group, FieldKind Kind, string[]? Options, string? Help)[] Definitions =
    [
        ("Sftp:Host", "Host", "Destination", FieldKind.Text, null, null),
        ("Sftp:Port", "Port", "Destination", FieldKind.Number, null, null),
        ("Sftp:Username", "Username", "Destination", FieldKind.Text, null, null),
        ("Sftp:AuthMethod", "Authentication", "Destination", FieldKind.Choice, ["Password", "PrivateKey"], "The password or key passphrase is a Secret: set it in the environment."),
        ("Sftp:PrivateKeyPath", "Private key file", "Destination", FieldKind.Path, null, null),
        (FingerprintKey, "Host Key Fingerprint", "Destination", FieldKind.Text, null, "The pinned identity of the server. A server presenting a different one is refused."),
        ("Sftp:RemoteRoot", "Remote root", "Destination", FieldKind.Text, null, "The server directory every Source is uploaded under, unless the Source has its own Remote Path."),
        ("Sftp:RemoteAccess", "Remote access", "Destination", FieldKind.Choice, ["Auto", "ReadWrite", "WriteOnly"], "WriteOnly: the account can upload but not read, list, delete or overwrite."),
        ("Sftp:UploadStrategy", "Upload strategy", "Destination", FieldKind.Choice, ["PartThenRename", "Direct"], null),
        ("Sftp:ConnectTimeoutSeconds", "Connect timeout (seconds)", "Destination", FieldKind.Number, null, null),
        ("Sftp:KeepAliveSeconds", "Keep-alive (seconds)", "Destination", FieldKind.Number, null, null),

        ("Upload:MaxParallelUploads", "Parallel uploads", "Upload", FieldKind.Number, null, "1 to 16 files at a time."),
        ("Upload:RehashAll", "Rehash all files", "Upload", FieldKind.Toggle, null, "Ignore the size and modified time shortcut and hash every file again."),
        ("Upload:VerifyAfterUpload", "Verification after upload", "Upload", FieldKind.Choice, Levels, "Checks each file just uploaded, before the rename."),
        ("Upload:VerifyRemote", "Verification of unchanged files", "Upload", FieldKind.Choice, Levels, "Checks the files that would be skipped as unchanged are still on the server."),
        ("Upload:VerifyTimeoutSeconds", "Verification timeout (seconds)", "Upload", FieldKind.Number, null, null),
        ("Retry:MaxAttempts", "Attempts per file", "Upload", FieldKind.Number, null, null),
        ("Retry:BaseDelaySeconds", "Retry delay (seconds)", "Upload", FieldKind.Number, null, null),
        ("Retry:MaxDelaySeconds", "Longest retry delay (seconds)", "Upload", FieldKind.Number, null, null),

        ("Ignore:UseDefaults", "Ignore the built-in junk files", "Ignore Rules", FieldKind.Toggle, null, ".DS_Store, Thumbs.db, desktop.ini and ._*"),
        ("Ignore:Files", "Ignored files (one relative path per line)", "Ignore Rules", FieldKind.Lines, null, null),
        ("Ignore:Patterns", "Ignored patterns (one regular expression per line)", "Ignore Rules", FieldKind.Lines, null, "Matched case-insensitively against the relative path."),
        ("Scan:MinFileAgeSeconds", "Minimum file age (seconds)", "Ignore Rules", FieldKind.Number, null, "Younger files are held back as Too Recent."),

        ("Archive:StagingPath", "Staging Area", "Archives", FieldKind.Path, null, "Where Archives are built before upload. Empty means inside the Data Directory."),
        ("Archive:MaxParallelBuilds", "Parallel Archive builds", "Archives", FieldKind.Number, null, null),
        ("Archive:MinFreeSpaceBytes", "Free space to keep (bytes)", "Archives", FieldKind.Number, null, null),
        ("Archive:WarnAboveBytes", "Warn above Archive size (bytes)", "Archives", FieldKind.Number, null, null),

        ("Manifest:JsonName", "Manifest file name", "Manifest", FieldKind.Text, null, null),
        ("Manifest:WriteFlat", "Also write the Flat Manifest", "Manifest", FieldKind.Toggle, null, "A manifest.sha256 that sha256sum -c understands."),
        ("Manifest:FlatName", "Flat Manifest file name", "Manifest", FieldKind.Text, null, null),

        ("State:Path", "Data Directory", "Data Directory", FieldKind.Path, null, "Empty means the machine-wide default shared by all accounts."),
        ("Report:Directory", "Report directory", "Reports and logs", FieldKind.Path, null, null),
        ("Report:Format", "Report format", "Reports and logs", FieldKind.Choice, ["Json", "Csv"], null),
        ("Logging:Directory", "Log directory", "Reports and logs", FieldKind.Path, null, "Empty means a logs folder in your per-user app data."),
        ("Logging:Level", "File log level", "Reports and logs", FieldKind.Choice, LogLevels, null),
        ("Logging:RetainDays", "Keep log files (days)", "Reports and logs", FieldKind.Number, null, null),
        ("Ui:LogLevel", "Log pane level", "Reports and logs", FieldKind.Choice, LogLevels, null),

        ("Ui:Theme", "Theme", "Appearance", FieldKind.Choice, ["Dark", "Light", "System"], null),
    ];

    private static readonly HashSet<string> IntegerKeys =
        Definitions.Where(d => d.Kind == FieldKind.Number).Select(d => d.Key).ToHashSet(StringComparer.OrdinalIgnoreCase);

    private readonly Configuration _configuration;
    private readonly Dictionary<string, SettingFieldViewModel> _byKey = new(StringComparer.OrdinalIgnoreCase);
    private LoadResult _load = new();
    private bool _sourcesLocked;
    private int _sourceCount;
    private bool _hasErrors;
    private bool _hasChanges;
    private string _saveMessage = "";

    public SettingsPageViewModel(Configuration configuration, Func<string, DataDirectoryAccess>? checkDataDirectory = null, Func<string, long>? freeSpace = null)
    {
        _configuration = configuration;
        SaveCommand = ReactiveCommand.Create(Save, this.WhenAnyValue(x => x.HasChanges, x => x.HasErrors, (changed, errors) => changed && !errors));
        RevertCommand = ReactiveCommand.Create(Reload);
        AddSourceCommand = ReactiveCommand.Create(AddSource, this.WhenAnyValue(x => x.SourcesEditable));
        RemoveSourceCommand = ReactiveCommand.Create<SourceEditorViewModel>(RemoveSource, this.WhenAnyValue(x => x.SourcesEditable));
        Reload();
    }

    public ObservableCollection<SettingFieldViewModel> Fields { get; } = [];
    public ObservableCollection<SourceEditorViewModel> Sources { get; } = [];

    /// <summary>Errors that belong to no field, one per line.</summary>
    public ObservableCollection<string> OtherErrors { get; } = [];
    public ObservableCollection<string> Warnings { get; } = [];

    public ReactiveCommand<Unit, Unit> SaveCommand { get; }
    public ReactiveCommand<Unit, Unit> RevertCommand { get; }
    public ReactiveCommand<Unit, Unit> AddSourceCommand { get; }
    public ReactiveCommand<SourceEditorViewModel, Unit> RemoveSourceCommand { get; }

    /// <summary>Opens a folder picker and returns the chosen folder, or null. The view sets it; the default picks nothing.</summary>
    public Func<Task<string?>> PickFolder { get; set; } = () => Task.FromResult<string?>(null);

    /// <summary>Whether the SFTP password and the key passphrase are set in the environment. Their values are never read here.</summary>
    public string SftpPasswordStatus { get; private set; } = "not set";
    public string SftpKeyPassphraseStatus { get; private set; } = "not set";

    public bool SourcesLocked
    {
        get => _sourcesLocked;
        private set
        {
            this.RaiseAndSetIfChanged(ref _sourcesLocked, value);
            this.RaisePropertyChanged(nameof(SourcesEditable));
        }
    }

    public bool SourcesEditable => !SourcesLocked;

    public bool HasErrors { get => _hasErrors; private set => this.RaiseAndSetIfChanged(ref _hasErrors, value); }
    public bool HasChanges { get => _hasChanges; private set => this.RaiseAndSetIfChanged(ref _hasChanges, value); }

    /// <summary>The outcome of the last Save, or empty.</summary>
    public string SaveMessage { get => _saveMessage; private set => this.RaiseAndSetIfChanged(ref _saveMessage, value); }

    public SettingFieldViewModel Field(string key) => _byKey[key];

    public bool TryGetField(string key, out SettingFieldViewModel field) => _byKey.TryGetValue(key, out field!);

    /// <summary>Reads the configuration again and drops every unsaved edit.</summary>
    public void Reload()
    {
        _load = _configuration.Load();
        Fields.Clear();
        _byKey.Clear();
        foreach (var (key, label, group, kind, options, help) in Definitions)
        {
            var original = kind == FieldKind.Lines ? string.Join('\n', _load.List(key)) : _load.Value(key) ?? "";
            var field = new SettingFieldViewModel(key, label, group, kind, original, _load.Setting(key), options, help, needsUnlock: key == FingerprintKey);
            field.ValueChanged += Revalidate;
            Fields.Add(field);
            _byKey[key] = field;
        }

        SourcesLocked = _load.Setting("Sources").Locked;
        Sources.Clear();
        foreach (var entry in _load.SourceEntries())
            AttachSource(new SourceEditorViewModel(entry, SourcesLocked, PickFolderAsync, RemoteRoot));
        _sourceCount = Sources.Count;

        SftpPasswordStatus = _load.Secrets.SftpPassword ? "set" : "not set";
        SftpKeyPassphraseStatus = _load.Secrets.SftpKeyPassphrase ? "set" : "not set";
        this.RaisePropertyChanged(nameof(SftpPasswordStatus));
        this.RaisePropertyChanged(nameof(SftpKeyPassphraseStatus));

        SaveMessage = "";
        Revalidate();
    }

    private Task<string?> PickFolderAsync() => PickFolder();

    private string RemoteRoot() => Field("Sftp:RemoteRoot").Value;

    private void AttachSource(SourceEditorViewModel source)
    {
        source.Edited += Revalidate;
        Sources.Add(source);
    }

    private void AddSource()
    {
        AttachSource(SourceEditorViewModel.Blank(PickFolderAsync, RemoteRoot));
        Revalidate();
    }

    private void RemoveSource(SourceEditorViewModel source)
    {
        Sources.Remove(source);
        Revalidate();
    }

    private bool SourcesChanged => !SourcesLocked && (Sources.Count != _sourceCount || Sources.Any(s => s.IsChanged));

    private string SecretStatusOf(SourceEditorViewModel source)
    {
        if (!source.IsS3) return "";
        var variable = Secrets.NormaliseSourceName(source.Name);
        var names = $"MIRES_S3_{variable}_ACCESS_KEY and MIRES_S3_{variable}_SECRET_KEY";
        return _load.Secrets.S3.TryGetValue(source.Name, out var status)
            ? $"Access key: {(status.AccessKeySet ? "set" : "not set")} · Secret key: {(status.SecretKeySet ? "set" : "not set")}. Supply them as {names}."
            : $"Supply the access and secret keys as {names}; whether they are set is shown once the Source is saved.";
    }

    private void Revalidate()
    {
        var changes = Changes();
        foreach (var field in Fields) field.Error = null;
        foreach (var source in Sources)
        {
            source.Error = "";
            source.Warning = "";
            source.SecretStatus = SecretStatusOf(source);
            source.RefreshPlaceholder();
        }
        OtherErrors.Clear();
        Warnings.Clear();

        var errors = new List<ConfigError>();
        foreach (var field in Fields.Where(f => IntegerKeys.Contains(f.Key) && f.Value.Length > 0 && !long.TryParse(f.Value, out _)))
            field.Error = "must be a whole number.";

        IReadOnlyList<ConfigError> warnings = _load.Warnings;
        if (!Fields.Any(f => f.HasError))
        {
            if (changes.Count == 0) errors.AddRange(_load.Errors);
            else
            {
                var check = _configuration.Check(changes);
                errors.AddRange(check.Errors);
                warnings = check.Warnings;
            }
        }

        foreach (var error in errors)
        {
            if (error.Key is not null && FieldFor(error.Key) is { } field) field.Error ??= error.Message;
            else if (SourceFor(error.Key, out var row, out var rest)) row.Error = Join(row.Error, $"{rest}: {error.Message}");
            else OtherErrors.Add(error.ToString());
        }
        foreach (var warning in warnings)
        {
            if (SourceFor(warning.Key, out var row, out var rest)) row.Warning = Join(row.Warning, $"{rest}: {warning.Message}");
            else Warnings.Add(warning.ToString());
        }

        HasErrors = Fields.Any(f => f.HasError) || Sources.Any(r => r.HasError) || OtherErrors.Count > 0;
        HasChanges = changes.Count > 0;
        SaveMessage = "";
    }

    private static string Join(string existing, string next) => existing.Length == 0 ? next : existing + " " + next;

    /// <summary>Maps <c>Sources:2:Path</c> to the third row and <c>Path</c>.</summary>
    private bool SourceFor(string? key, out SourceEditorViewModel row, out string rest)
    {
        row = null!;
        rest = "";
        var parts = key?.Split(':', 3);
        if (parts is not { Length: 3 } || !parts[0].Equals("Sources", StringComparison.OrdinalIgnoreCase)
            || !int.TryParse(parts[1], out var index) || index < 0 || index >= Sources.Count)
            return false;
        row = Sources[index];
        rest = parts[2];
        return true;
    }

    private SettingFieldViewModel? FieldFor(string key)
    {
        if (_byKey.TryGetValue(key, out var exact)) return exact;
        return Fields.FirstOrDefault(f => f.Kind == FieldKind.Lines && key.StartsWith(f.Key + ":", StringComparison.OrdinalIgnoreCase));
    }

    /// <summary>The flat changes for <see cref="Configuration.Save"/>.</summary>
    private Dictionary<string, string?> Changes()
    {
        var changes = new Dictionary<string, string?>(StringComparer.OrdinalIgnoreCase);
        foreach (var field in Fields.Where(f => f.IsChanged && f.IsEditable))
        {
            if (field.Kind == FieldKind.Lines)
            {
                var lines = field.Value.Split('\n').Select(l => l.Trim()).Where(l => l.Length > 0).ToList();
                if (lines.Count == 0) changes[field.Key] = "[]";
                else
                {
                    changes[field.Key] = null;
                    for (var i = 0; i < lines.Count; i++) changes[$"{field.Key}:{i}"] = lines[i];
                }
            }
            else changes[field.Key] = field.Value.Trim().Length == 0 ? null : field.Value.Trim();
        }
        if (SourcesChanged)
        {
            if (Sources.Count == 0) changes["Sources"] = "[]";
            else
            {
                changes["Sources"] = null;
                for (var i = 0; i < Sources.Count; i++)
                    foreach (var (key, value) in Sources[i].ToEntry())
                        changes[$"Sources:{i}:{key}"] = value;
            }
        }
        return changes;
    }

    private void Save()
    {
        var result = _configuration.Save(Changes());
        if (!result.Succeeded)
        {
            SaveMessage = "Not saved: " + string.Join(" ", result.Errors.Select(e => e.ToString()));
            return;
        }

        Reload();
        SaveMessage = "Saved to your User Overrides.";
    }
}

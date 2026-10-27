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
        ("Sftp:AuthMethod", "Authentication", "Destination", FieldKind.Choice, ["Password", "PrivateKey"], "The password or key passphrase is a Secret: set it under Secrets below, or in the environment."),
        ("Sftp:PrivateKeyPath", "Private key file", "Destination", FieldKind.Text, null, null),
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
    private readonly CliOptions? _cli;
    private readonly Func<string, DataDirectoryAccess> _check;
    private readonly Func<string, long> _freeSpace;
    private readonly string _defaultDataDirectory = DataDirectory.Resolve(null, null, DataDirectory.CurrentPlatform, Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData));
    private string? _checkedPath;
    private string? _stagingKey;
    private readonly Dictionary<string, SettingFieldViewModel> _byKey = new(StringComparer.OrdinalIgnoreCase);
    private LoadResult _load = new();
    private SecretStatus _secrets = SecretStatus.None;
    private bool _sourcesLocked;
    private int _sourceCount;
    private bool _hasErrors;
    private bool _hasChanges;
    private string _saveMessage = "";

    public SettingsPageViewModel(Configuration configuration, Func<string, DataDirectoryAccess>? checkDataDirectory = null, Func<string, long>? freeSpace = null, CliOptions? cli = null)
    {
        _configuration = configuration;
        _cli = cli;
        _check = checkDataDirectory ?? (path => DataDirectory.Check(path));
        _freeSpace = freeSpace ?? DataDirectory.FreeSpaceBytes;
        SftpPassword = NewSecretEntry(Secrets.SftpPasswordName, "SFTP password");
        SftpKeyPassphrase = NewSecretEntry(Secrets.SftpKeyPassphraseName, "SFTP key passphrase");
        UnlockFingerprintCommand = ReactiveCommand.CreateFromTask(UnlockFingerprint);
        RecheckDataDirectoryCommand = ReactiveCommand.Create(() => CheckDataDirectory(force: true));
        CopyFixCommandCommand = ReactiveCommand.CreateFromTask(() => CopyToClipboard(DataDirectoryFixCommand));
        SaveCommand = ReactiveCommand.Create(Save, this.WhenAnyValue(x => x.HasChanges, x => x.HasErrors, (changed, errors) => changed && !errors));
        RevertCommand = ReactiveCommand.Create(Reload);
        AddSourceCommand = ReactiveCommand.Create(AddSource, this.WhenAnyValue(x => x.SourcesEditable));
        RemoveSourceCommand = ReactiveCommand.Create<SourceEditorViewModel>(RemoveSource, this.WhenAnyValue(x => x.SourcesEditable));
        Reload();
    }

    /// <summary>Raised after a successful Save, so the rest of the window can read the configuration again.</summary>
    public event Action? Saved;

    public ObservableCollection<SettingFieldViewModel> Fields { get; } = [];
    public ObservableCollection<SettingsGroupViewModel> Groups { get; } = [];
    public ObservableCollection<SourceEditorViewModel> Sources { get; } = [];

    /// <summary>The global Archive Rules, tried after each Source's own.</summary>
    public ArchiveRulesViewModel ArchiveRules { get; private set; } = new([], locked: false);

    public static IReadOnlyList<string> SourceTypes { get; } = ["Directory", "S3"];

    /// <summary>Errors that belong to no field, one per line.</summary>
    public ObservableCollection<string> OtherErrors { get; } = [];
    public ObservableCollection<string> Warnings { get; } = [];

    public ReactiveCommand<Unit, Unit> SaveCommand { get; }
    public ReactiveCommand<Unit, Unit> RevertCommand { get; }
    public ReactiveCommand<Unit, Unit> UnlockFingerprintCommand { get; }
    public ReactiveCommand<Unit, Unit> RecheckDataDirectoryCommand { get; }
    public ReactiveCommand<Unit, Unit> CopyFixCommandCommand { get; }
    public ReactiveCommand<Unit, Unit> AddSourceCommand { get; }
    public ReactiveCommand<SourceEditorViewModel, Unit> RemoveSourceCommand { get; }

    /// <summary>Opens a folder picker and returns the chosen folder, or null. The view sets it; the default picks nothing.</summary>
    public Func<Task<string?>> PickFolder { get; set; } = () => Task.FromResult<string?>(null);

    /// <summary>Asks the user to confirm (title, message); the view shows a dialog. The default declines.</summary>
    public Func<string, string, Task<bool>> Confirm { get; set; } = (_, _) => Task.FromResult(false);

    /// <summary>Puts text on the clipboard. The view sets it.</summary>
    public Func<string, Task> CopyToClipboard { get; set; } = _ => Task.CompletedTask;

    // ---- Data Directory ----

    public string DataDirectoryPath { get; private set; } = "";
    public string DataDirectoryStatus { get; private set; } = "";
    public string DataDirectoryFreeSpace { get; private set; } = "";
    public string DataDirectoryDatabaseSize { get; private set; } = "";
    public string DataDirectoryFixCommand { get; private set; } = "";
    public string DataDirectoryProblem { get; private set; } = "";
    public bool HasDataDirectoryProblem => DataDirectoryProblem.Length > 0;
    public bool DataDirectoryOnNetworkShare { get; private set; }
    public string SplitStateWarning { get; private set; } = "";
    public bool HasSplitStateWarning => SplitStateWarning.Length > 0;
    public string StagingWarning { get; private set; } = "";
    public bool HasStagingWarning => StagingWarning.Length > 0;

    /// <summary>Whether the SFTP password and the key passphrase are set in the environment. Their values are never read here.</summary>
    public string SftpPasswordStatus { get; private set; } = "not set";
    public string SftpKeyPassphraseStatus { get; private set; } = "not set";

    public SecretEntryViewModel SftpPassword { get; }
    public SecretEntryViewModel SftpKeyPassphrase { get; }

    private SecretEntryViewModel NewSecretEntry(string name, string label) =>
        new(name, label, _configuration.SetSecret, _configuration.ClearSecret, () => { RefreshSecrets(); Revalidate(); });

    /// <summary>Reads where each Secret comes from again, without touching unsaved edits.</summary>
    private void RefreshSecrets()
    {
        var status = _secrets = _configuration.LoadSecretStatus(_load.Config?.Sources ?? []);
        SftpPassword.Refresh(status.OriginOf(Secrets.SftpPasswordName), status.StoreProblem);
        SftpKeyPassphrase.Refresh(status.OriginOf(Secrets.SftpKeyPassphraseName), status.StoreProblem);
        foreach (var source in Sources) SyncKeyEntries(source);
        SftpPasswordStatus = status.SftpPassword ? "set" : "not set";
        SftpKeyPassphraseStatus = status.SftpKeyPassphrase ? "set" : "not set";
        this.RaisePropertyChanged(nameof(SftpPasswordStatus));
        this.RaisePropertyChanged(nameof(SftpKeyPassphraseStatus));
    }

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
        _load = _configuration.Load(_cli);
        Fields.Clear();
        _byKey.Clear();
        foreach (var (key, label, group, kind, options, help) in Definitions)
        {
            var original = kind == FieldKind.Lines ? string.Join('\n', _load.List(key)) : _load.Value(key) ?? "";
            var field = new SettingFieldViewModel(key, label, group, kind, original, _load.Setting(key), options, help, needsUnlock: key == FingerprintKey);
            field.ValueChanged += Revalidate;
            if (kind == FieldKind.Path) field.BrowseCommand = ReactiveCommand.CreateFromTask(async () =>
            {
                if (await PickFolder() is { } picked) field.Value = picked;
            });
            if (key == FingerprintKey) field.UnlockCommand = UnlockFingerprintCommand;
            Fields.Add(field);
            _byKey[key] = field;
        }

        Groups.Clear();
        foreach (var group in Fields.GroupBy(f => f.Group))
            Groups.Add(new SettingsGroupViewModel(group.Key, group.ToList()));

        SourcesLocked = _load.Setting("Sources").Locked;
        Sources.Clear();
        foreach (var entry in _load.SourceEntries())
            AttachSource(new SourceEditorViewModel(entry, SourcesLocked, PickFolderAsync, RemoteRoot));
        _sourceCount = Sources.Count;

        ArchiveRules = new ArchiveRulesViewModel(_load.ListEntries("Archive:Rules"), _load.Setting("Archive:Rules").Locked);
        ArchiveRules.Edited += Revalidate;
        this.RaisePropertyChanged(nameof(ArchiveRules));

        RefreshSecrets();

        SaveMessage = "";
        _checkedPath = null;
        _stagingKey = null;
        Revalidate();
    }

    private async Task UnlockFingerprint()
    {
        var field = Field(FingerprintKey);
        if (field.IsLocked) return;
        const string message = "The Host Key Fingerprint pins the identity of the SFTP server. Changing it makes Runs trust whatever server presents the new fingerprint, "
            + "and a wrong value stops all uploads. Only change it when the server's key has changed and you have verified the new fingerprint with its administrator.";
        if (await Confirm("Change the Host Key Fingerprint?", message)) field.Unlock();
    }

    private string EffectiveDataDirectory()
    {
        var path = Field("State:Path").Value.Trim();
        return path.Length > 0 ? path : _defaultDataDirectory;
    }

    private void CheckDataDirectory(bool force)
    {
        var path = EffectiveDataDirectory();
        var statePath = Field("State:Path").Value.Trim();
        SplitStateWarning = statePath.Length > 0 && !SamePath(statePath, _defaultDataDirectory)
            ? $"State:Path points to '{statePath}', not the shared Data Directory '{_defaultDataDirectory}'. The Upload State kept there is not shared with other accounts on this machine, "
              + "so their Runs, History and cancel requests will be separate from yours."
            : "";
        if (!force && path == _checkedPath)
        {
            RaiseDataDirectory();
            return;
        }

        _checkedPath = path;
        var access = _check(path);
        DataDirectoryPath = access.Path;
        DataDirectoryStatus = access.Writable
            ? $"Writable by {access.Account}" + (access.Group is { } group ? $" (group {group})" : "")
            : access.Exists ? $"Not writable by {access.Account}" : "Does not exist";
        DataDirectoryFreeSpace = $"{FormatBytes(access.FreeSpaceBytes)} free";
        DataDirectoryDatabaseSize = FormatBytes(access.DatabaseSizeBytes);
        DataDirectoryFixCommand = access.Problem is null ? "" : access.FixCommand;
        DataDirectoryProblem = access.Problem ?? "";
        DataDirectoryOnNetworkShare = access.OnNetworkShare;
        _stagingKey = null;
        RaiseDataDirectory();
    }

    private void RaiseDataDirectory()
    {
        foreach (var name in new[]
        {
            nameof(DataDirectoryPath), nameof(DataDirectoryStatus), nameof(DataDirectoryFreeSpace), nameof(DataDirectoryDatabaseSize),
            nameof(DataDirectoryFixCommand), nameof(DataDirectoryProblem), nameof(HasDataDirectoryProblem), nameof(DataDirectoryOnNetworkShare),
            nameof(SplitStateWarning), nameof(HasSplitStateWarning),
        })
            this.RaisePropertyChanged(name);
    }

    private void CheckStaging()
    {
        var configured = Field("Archive:StagingPath").Value.Trim();
        var path = configured.Length > 0 ? configured : System.IO.Path.Combine(DataDirectoryPath, "staging");
        var required = long.TryParse(Field("Archive:MinFreeSpaceBytes").Value, out var min) ? min : 0;
        var key = path + "|" + required;
        if (key == _stagingKey) return;
        _stagingKey = key;

        var free = _freeSpace(path);
        StagingWarning = free < required
            ? $"The Staging Area '{path}' has {FormatBytes(free)} free but {FormatBytes(required)} must stay free: Archives will fail with InsufficientStagingSpace. Free up space or choose another Staging Area."
            : "";
        this.RaisePropertyChanged(nameof(StagingWarning));
        this.RaisePropertyChanged(nameof(HasStagingWarning));
    }

    private static bool SamePath(string a, string b)
    {
        static string Norm(string p) => System.IO.Path.GetFullPath(p).TrimEnd(System.IO.Path.DirectorySeparatorChar, System.IO.Path.AltDirectorySeparatorChar);
        return string.Equals(Norm(a), Norm(b), OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal);
    }

    internal static string FormatBytes(long bytes)
    {
        string[] units = ["B", "KiB", "MiB", "GiB", "TiB"];
        var value = (double)bytes;
        var unit = 0;
        while (value >= 1024 && unit < units.Length - 1)
        {
            value /= 1024;
            unit++;
        }
        return unit == 0 ? $"{bytes} B" : string.Create(System.Globalization.CultureInfo.InvariantCulture, $"{value:0.0} {units[unit]}");
    }

    private void UpdateNotes()
    {
        Field("Upload:VerifyAfterUpload").Note = Field("Upload:VerifyAfterUpload").Value switch
        {
            "Hash" => "Hash runs a command on the server for every uploaded file; very large files take a while. Needs a shell on the server.",
            "ReadBack" => "ReadBack downloads every uploaded file again and hashes it: it doubles the bandwidth and the time of each upload.",
            _ => null,
        };
        Field("Upload:VerifyRemote").Note = Field("Upload:VerifyRemote").Value switch
        {
            "Hash" or "ReadBack" => "This is expensive: every unchanged file is checked on the server on every Run"
                + (Field("Upload:VerifyRemote").Value == "ReadBack" ? " by downloading it again" : " by hashing it there")
                + ", which takes long when there are thousands of unchanged files. Size is cheap.",
            _ => null,
        };
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

    /// <summary>True when the Sources list differs from what was loaded: one added, one removed, or one edited.</summary>
    public bool SourcesChanged => !SourcesLocked && (Sources.Count != _sourceCount || Sources.Any(s => s.IsChanged));

    /// <summary>Gives a saved S3 Source entries for its keys, keeps them current, and drops them when the Source is renamed or retyped.</summary>
    private void SyncKeyEntries(SourceEditorViewModel source)
    {
        var saved = source.IsS3 && !string.IsNullOrEmpty(source.Name) && _secrets.S3.ContainsKey(source.Name);
        if (!saved)
        {
            source.AccessKey = null;
            source.SecretKey = null;
            return;
        }

        var access = Secrets.S3Name(source.Name, "access-key");
        var secret = Secrets.S3Name(source.Name, "secret-key");
        if (source.AccessKey?.Name != access) source.AccessKey = NewSecretEntry(access, "Access key");
        if (source.SecretKey?.Name != secret) source.SecretKey = NewSecretEntry(secret, "Secret key");
        source.AccessKey!.Refresh(_secrets.OriginOf(access), _secrets.StoreProblem);
        source.SecretKey!.Refresh(_secrets.OriginOf(secret), _secrets.StoreProblem);
    }

    private string SecretStatusOf(SourceEditorViewModel source)
    {
        if (!source.IsS3) return "";
        var variable = Secrets.NormaliseSourceName(source.Name);
        var names = $"MIRES_S3_{variable}_ACCESS_KEY and MIRES_S3_{variable}_SECRET_KEY";
        return _secrets.S3.TryGetValue(source.Name, out var status)
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
            SyncKeyEntries(source);
            source.SecretStatus = SecretStatusOf(source);
            source.RefreshPlaceholder();
        }
        ArchiveRules.Error = "";
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
                var check = _configuration.Check(changes, _cli);
                errors.AddRange(check.Errors);
                warnings = check.Warnings;
            }
        }

        foreach (var error in errors)
        {
            if (error.Key is not null && FieldFor(error.Key) is { } field) field.Error ??= error.Message;
            else if (SourceFor(error.Key, out var row, out var rest)) row.Error = Join(row.Error, $"{rest}: {error.Message}");
            else if (error.Key?.StartsWith("Archive:Rules", StringComparison.OrdinalIgnoreCase) == true) ArchiveRules.Error = Join(ArchiveRules.Error, error.ToString());
            else OtherErrors.Add(error.ToString());
        }
        foreach (var warning in warnings)
        {
            if (SourceFor(warning.Key, out var row, out var rest)) row.Warning = Join(row.Warning, $"{rest}: {warning.Message}");
            else Warnings.Add(warning.ToString());
        }

        UpdateNotes();
        CheckDataDirectory(force: false);
        CheckStaging();
        HasErrors = Fields.Any(f => f.HasError) || Sources.Any(r => r.HasError) || ArchiveRules.HasError || OtherErrors.Count > 0;
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
        if (ArchiveRules.IsChanged)
        {
            if (ArchiveRules.Rules.Count == 0) changes["Archive:Rules"] = "[]";
            else
            {
                changes["Archive:Rules"] = null;
                foreach (var (key, value) in ArchiveRules.ToFlat("Archive:Rules")) changes[key] = value;
            }
        }
        return changes;
    }

    /// <summary>Says where the saved keys went: the Sources and Sftp settings to Machine Config, the rest to User Overrides.</summary>
    private static string SavedMessage(IReadOnlyList<string> keys)
    {
        var machine = keys.Any(k => k.Equals("Sources", StringComparison.OrdinalIgnoreCase) || k.StartsWith("Sources:", StringComparison.OrdinalIgnoreCase)
            || k.StartsWith("Sftp:", StringComparison.OrdinalIgnoreCase));
        var user = keys.Any(k => !(k.Equals("Sources", StringComparison.OrdinalIgnoreCase) || k.StartsWith("Sources:", StringComparison.OrdinalIgnoreCase)
            || k.StartsWith("Sftp:", StringComparison.OrdinalIgnoreCase)));
        return (machine, user) switch
        {
            (true, true) => "Saved to the Machine Config (Sources, Destination) and to your User Overrides.",
            (true, false) => "Saved to the Machine Config (appsettings.json).",
            _ => "Saved to your User Overrides.",
        };
    }

    private void Save()
    {
        var result = _configuration.Save(Changes(), _cli);
        if (!result.Succeeded)
        {
            SaveMessage = "Not saved: " + string.Join(" ", result.Errors.Select(e => e.ToString()));
            return;
        }

        Reload();
        SaveMessage = SavedMessage(result.WrittenKeys);
        Saved?.Invoke();
    }
}

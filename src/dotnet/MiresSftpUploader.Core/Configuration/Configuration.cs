using System.Text.Json;
using System.Text.RegularExpressions;
using Microsoft.Extensions.Configuration;

namespace MiresSftpUploader.Core;

public enum ConfigLayer { Default, Machine, User, Environment, Cli }

public sealed record ConfigError(string? Key, string Message)
{
    public override string ToString() => Key is null ? Message : $"{Key}: {Message}";
}

/// <summary>Where a setting's effective value comes from and whether the UI may edit it.</summary>
public sealed record SettingInfo(ConfigLayer Layer, bool Locked);

public sealed record LoadResult
{
    /// <summary>Null when <see cref="Errors"/> is not empty.</summary>
    public AppConfig? Config { get; init; }
    public IReadOnlyList<ConfigError> Errors { get; init; } = [];
    /// <summary>Problems that do not stop a Run, such as a Directory Source whose path does not exist yet (an error when headless).</summary>
    public IReadOnlyList<ConfigError> Warnings { get; init; } = [];
    public SecretStatus Secrets { get; init; } = SecretStatus.None;
    public bool MachineConfigWritable { get; init; }
    internal IReadOnlyDictionary<string, SettingInfo> Keys { get; init; } = new Dictionary<string, SettingInfo>();
    internal IReadOnlyDictionary<string, string> Values { get; init; } = new Dictionary<string, string>();

    /// <summary>
    /// The effective flat keys under a top-level section the program does not bind itself (such as <c>NLog</c>), with the
    /// section name stripped: <c>variables:MinLevel</c>, <c>rules:10_file:writeTo</c>. Empty when there is no such section.
    /// </summary>
    public IReadOnlyDictionary<string, string> Section(string name)
    {
        var prefix = name + ":";
        return Values
            .Where(kv => kv.Key.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
            .ToDictionary(kv => kv.Key[prefix.Length..], kv => kv.Value, StringComparer.OrdinalIgnoreCase);
    }

    public bool Succeeded => Errors.Count == 0;

    /// <summary>The effective text of a scalar key (the documented default when no layer sets it); null for a list, an unknown key, or a key with no default.</summary>
    public string? Value(string key) => Values.TryGetValue(key, out var set) ? set : Configuration.DefaultText(key);

    /// <summary>The effective elements of a list of plain values such as <c>Ignore:Files</c>, in order; empty when no layer defines it.</summary>
    public IReadOnlyList<string> List(string key) =>
        Values
            .Select(kv => (Key: kv.Key, Value: kv.Value))
            .Where(kv => kv.Key.StartsWith(key + ":", StringComparison.OrdinalIgnoreCase) && int.TryParse(kv.Key[(key.Length + 1)..], out _))
            .OrderBy(kv => int.Parse(kv.Key[(key.Length + 1)..]))
            .Select(kv => kv.Value)
            .ToList();

    /// <summary>
    /// The effective settings of each Source as flat keys relative to the Source (<c>Name</c>, <c>Ignore:Files:0</c>,
    /// <c>AfterUpload:OnSuccess:Path</c>), in list order. Lets the Settings screen rewrite the list without losing the keys it does not edit.
    /// </summary>
    public IReadOnlyList<IReadOnlyDictionary<string, string>> SourceEntries() => ListEntries("Sources");

    /// <summary>
    /// The effective elements of a list of objects such as <c>Archive:Rules</c> as flat keys relative to each element
    /// (<c>Name</c>, <c>Pattern</c>), in list order.
    /// </summary>
    public IReadOnlyList<IReadOnlyDictionary<string, string>> ListEntries(string listKey)
    {
        var depth = listKey.Split(':').Length;
        var prefix = listKey + ":";
        var entries = new SortedDictionary<int, Dictionary<string, string>>();
        foreach (var (key, value) in Values)
        {
            if (!key.StartsWith(prefix, StringComparison.OrdinalIgnoreCase)) continue;
            var segments = key.Split(':');
            if (segments.Length < depth + 2 || !int.TryParse(segments[depth], out var index)) continue;
            if (!entries.TryGetValue(index, out var entry)) entries[index] = entry = new(StringComparer.OrdinalIgnoreCase);
            entry[string.Join(':', segments[(depth + 1)..])] = value;
        }
        return entries.Values.Select(e => (IReadOnlyDictionary<string, string>)e).ToList();
    }

    /// <summary>
    /// The layer and writability of a key such as <c>Sftp:Host</c> or <c>Sources</c> (an array reports the layer that defines it).
    /// A key no layer sets is a Default and editable.
    /// </summary>
    public SettingInfo Setting(string key)
    {
        if (Keys.TryGetValue(key, out var exact)) return exact;
        var under = key + ":";
        foreach (var (k, info) in Keys)
            if (k.StartsWith(under, StringComparison.OrdinalIgnoreCase)) return info;
        return new SettingInfo(ConfigLayer.Default, Configuration.IsMachineScoped(key) && !MachineConfigWritable);
    }
}

/// <summary>The resolved Data Directory path and access group, or the errors that stopped the lookup.</summary>
public sealed record DataDirectorySettings(string Path, string? AccessGroup, IReadOnlyList<ConfigError> Errors);

public sealed record SaveResult(IReadOnlyList<ConfigError> Errors)
{
    public bool Succeeded => Errors.Count == 0;
    /// <summary>The keys written to User Overrides; empty when nothing changed.</summary>
    public IReadOnlyList<string> WrittenKeys { get; init; } = [];
}

/// <summary>What <see cref="Configuration.Check"/> found: the errors that would stop a Save, and the warnings that would not.</summary>
public sealed record SaveCheck(IReadOnlyList<ConfigError> Errors, IReadOnlyList<ConfigError> Warnings)
{
    public bool Succeeded => Errors.Count == 0;
}

public sealed record ConfigurationLocations(
    string MachineConfigPath,
    string UserOverridesPath,
    IReadOnlyDictionary<string, string?> Environment,
    string? SecretStorePath = null,
    IMachineIdentity? Identity = null)
{
    public const string SecretStoreFileName = "secrets.db";

    public const string MachineFileName = "appsettings.json";
    public const string UserFileName = "appsettings.user.json";

    /// <summary>Machine Config next to the executable, User Overrides in the per-user app-data directory, the real environment.</summary>
    public static ConfigurationLocations Default()
    {
        var env = new Dictionary<string, string?>(StringComparer.OrdinalIgnoreCase);
        foreach (System.Collections.DictionaryEntry e in System.Environment.GetEnvironmentVariables())
            env[(string)e.Key] = (string?)e.Value;
        return new ConfigurationLocations(
            Path.Combine(AppContext.BaseDirectory, MachineFileName),
            Path.Combine(UserDataDirectory(), UserFileName),
            env,
            Path.Combine(UserDataDirectory(), SecretStoreFileName),
            new OsMachineIdentity());
    }

    public static string UserDataDirectory()
    {
        if (OperatingSystem.IsWindows())
            return Path.Combine(System.Environment.GetFolderPath(System.Environment.SpecialFolder.ApplicationData), "MiresSftpUploader");
        if (OperatingSystem.IsMacOS())
            return Path.Combine(System.Environment.GetFolderPath(System.Environment.SpecialFolder.UserProfile), "Library", "Application Support", "MiresSftpUploader");
        var xdg = System.Environment.GetEnvironmentVariable("XDG_CONFIG_HOME");
        var root = string.IsNullOrEmpty(xdg) ? Path.Combine(System.Environment.GetFolderPath(System.Environment.SpecialFolder.UserProfile), ".config") : xdg;
        return Path.Combine(root, "mires-sftp-uploader");
    }
}

/// <summary>
/// Layered settings: Machine Config, then User Overrides, then <c>MIRES_*</c> environment variables, then CLI flags.
/// An array is replaced whole by the highest layer that defines it. Secrets come from environment variables or the Secret Store
/// and are never part of <see cref="AppConfig"/>.
/// </summary>
public sealed class Configuration(ConfigurationLocations locations)
{
    public const int ConfigVersion = 1;

    public LoadResult Load(CliOptions? cli = null, bool headless = false)
    {
        var layers = ReadLayers(cli ?? new CliOptions(), out var errors);
        var machineWritable = IsDirectoryWritable(Path.GetDirectoryName(Path.GetFullPath(locations.MachineConfigPath))!);
        if (layers is null)
            return new LoadResult { Errors = errors, MachineConfigWritable = machineWritable };
        return Evaluate(layers, headless, machineWritable);
    }

    /// <summary>
    /// Where the Data Directory is and which group may use it, without validating the rest of the configuration (an
    /// administrator runs <c>--init-data-dir</c> before the Sources and the server are set up). The path comes from
    /// <c>State:Path</c> in any layer (<c>MIRES_DATA_DIR</c> and <c>--data-dir</c> set it); <c>State:AccessGroup</c> is read
    /// from Machine Config and the environment only.
    /// </summary>
    public DataDirectorySettings ResolveDataDirectory(CliOptions? cli = null)
    {
        var layers = ReadLayers(cli ?? new CliOptions(), out var errors, machineRequired: false);
        if (layers is null) return new DataDirectorySettings("", null, errors);

        var path = Merge(layers).Values.GetValueOrDefault("State:Path");
        var group = layers.Environment.Values.GetValueOrDefault(GroupKey) ?? layers.Machine.Values.GetValueOrDefault(GroupKey);
        return new DataDirectorySettings(
            DataDirectory.Resolve(path, null, DataDirectory.CurrentPlatform, System.Environment.GetFolderPath(System.Environment.SpecialFolder.CommonApplicationData)),
            string.IsNullOrWhiteSpace(group) ? null : group,
            []);
    }

    private const string GroupKey = "State:AccessGroup";
    private const string VerifyCommandKey = "Upload:VerifyCommand";

    private LoadResult Evaluate(Layers layers, bool headless, bool machineWritable)
    {
        var errors = new List<ConfigError>();
        var warnings = new List<ConfigError>();
        if (layers.User.Values.Remove(VerifyCommandKey))
            warnings.Add(new(VerifyCommandKey, "is ignored in User Overrides. Set it in Machine Config or the environment."));
        foreach (var ignored in layers.IgnoredUserKeys)
            warnings.Add(new(ignored, "is ignored in User Overrides. The Sources and the Sftp settings are kept in Machine Config (appsettings.json) and saved there."));
        var merged = Merge(layers);
        var keys = merged.Layers.ToDictionary(
            kv => kv.Key,
            kv => new SettingInfo(kv.Value, IsLocked(kv.Value, machineWritable) || (IsMachineScoped(kv.Key) && !machineWritable)),
            StringComparer.OrdinalIgnoreCase);

        var config = Bind(merged.Values, errors);
        foreach (var (layer, file) in new[] { ("Machine Config", layers.Machine), ("User Overrides", layers.User) })
            foreach (var key in file.Values.Keys.Where(k => SecretLikeKey.IsMatch(k)))
                warnings.Add(new(key, $"{layer} must not hold a Secret; the value is ignored. Set it in an environment variable."));
        if (layers.User.Values.ContainsKey(GroupKey))
            warnings.Add(new(GroupKey, "is ignored in User Overrides. Set it in Machine Config or the environment."));
        if (config is not null)
            ConfigValidator.Validate(config, headless, errors, warnings);

        return new LoadResult
        {
            Config = errors.Count == 0 ? config : null,
            Errors = errors,
            Warnings = warnings,
            MachineConfigWritable = machineWritable,
            Keys = keys,
            Values = merged.Values,
            Secrets = LoadSecrets().Status(config?.Sources ?? []),
        };
    }

    /// <summary>
    /// The settings that describe where files come from and where they go (<c>Sources</c> and <c>Sftp:*</c>): every user of the
    /// machine shares them, so they live in Machine Config and are saved there. User Overrides cannot hold them.
    /// </summary>
    internal static bool IsMachineScoped(string key) =>
        key.Equals("Sources", StringComparison.OrdinalIgnoreCase) || key.StartsWith("Sources:", StringComparison.OrdinalIgnoreCase)
        || key.Equals("Sftp", StringComparison.OrdinalIgnoreCase) || key.StartsWith("Sftp:", StringComparison.OrdinalIgnoreCase);

    private static bool IsLocked(ConfigLayer layer, bool machineWritable) =>
        layer is ConfigLayer.Environment or ConfigLayer.Cli || (layer == ConfigLayer.Machine && !machineWritable);

    /// <summary>
    /// Writes <paramref name="changes"/> (flat key to new value; <c>null</c> drops the User Override; <c>[]</c> empties a list)
    /// to User Overrides, or to Machine Config for the Sources and Sftp settings, after re-validating the result. Only keys
    /// whose value changes are written. Locked Settings and Secrets are rejected. When a change touches a list, the whole effective list is saved with it, since a list is
    /// replaced whole.
    /// </summary>
    public SaveResult Save(IReadOnlyDictionary<string, string?> changes, CliOptions? cli = null)
    {
        var plan = Plan(changes, cli);
        if (plan.Errors.Count > 0) return new SaveResult(plan.Errors);
        if (plan.Written.Count == 0) return new SaveResult([]);

        try
        {
            if (plan.WritesMachine) WriteAtomically(locations.MachineConfigPath, UserFile.ToJson(plan.NextMachine!, ConfigVersion));
            if (plan.WritesUser) WriteAtomically(locations.UserOverridesPath, UserFile.ToJson(plan.Next!, ConfigVersion));
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException)
        {
            return new SaveResult([new(null, $"Could not write the settings: {e.Message}")]);
        }
        return new SaveResult([]) { WrittenKeys = plan.Written };
    }

    /// <summary>
    /// Validates what <see cref="Save"/> would write, without writing: the same errors Save would return, plus the warnings
    /// of the resulting configuration (a missing Directory path, for example). The Settings screen calls it on every edit.
    /// </summary>
    public SaveCheck Check(IReadOnlyDictionary<string, string?> changes, CliOptions? cli = null)
    {
        var plan = Plan(changes, cli);
        return new SaveCheck(plan.Errors, plan.Warnings);
    }

    private sealed record SavePlan(
        IReadOnlyList<ConfigError> Errors, IReadOnlyList<ConfigError> Warnings, IReadOnlyList<string> Written,
        FlatSettings? Next, FlatSettings? NextMachine = null, bool WritesUser = false, bool WritesMachine = false);

    private static FlatSettings Copy(FlatSettings source)
    {
        var copy = new FlatSettings();
        foreach (var (k, v) in source.Values) copy.Values[k] = v;
        foreach (var e in source.EmptyArrays) copy.EmptyArrays.Add(e);
        return copy;
    }

    private SavePlan Plan(IReadOnlyDictionary<string, string?> changes, CliOptions? cli)
    {
        var layers = ReadLayers(cli ?? new CliOptions(), out var errors);
        if (layers is null) return new SavePlan(errors, [], [], null);
        var machineWritable = IsDirectoryWritable(Path.GetDirectoryName(Path.GetFullPath(locations.MachineConfigPath))!);

        var current = Merge(layers);
        var next = Copy(layers.User);
        var nextMachine = Copy(layers.Machine);
        FlatSettings TargetOf(string key) => IsMachineScoped(key) ? nextMachine : next;

        foreach (var key in changes.Keys)
        {
            if (SecretLikeKey.IsMatch(key))
                errors.Add(new(key, "is a Secret and is never saved; set it in an environment variable."));
            else if (key.Equals(GroupKey, StringComparison.OrdinalIgnoreCase) || key.Equals(VerifyCommandKey, StringComparison.OrdinalIgnoreCase))
                errors.Add(new(key, "can only be set in Machine Config or the environment."));
            else if (IsLocked(LayerOf(current, key), machineWritable) || (IsMachineScoped(key) && !machineWritable))
                errors.Add(new(key, "is a Locked Setting (supplied by the environment, a CLI flag or a Machine Config you cannot write)."));
        }
        if (errors.Count > 0) return new SavePlan(errors, [], [], null);

        var cleared = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var (key, value) in changes.Where(c => c.Value is null || c.Value == "[]"))
        {
            RemoveUnder(TargetOf(key), key);
            if (value == "[]") TargetOf(key).EmptyArrays.Add(key);
            cleared.Add(key);
        }

        var written = new List<string>();
        foreach (var (key, value) in changes.Where(c => c.Value is not null && c.Value != "[]"))
        {
            var root = FlatSettings.ArrayRootOf(key);
            // Under a list that this save clears the list is rewritten whole, so a value equal to the current one must still be written.
            var rewritten = root is not null && cleared.Contains(root);
            var effective = current.Values.TryGetValue(key, out var set) ? set : DefaultText(key);
            if (!rewritten && string.Equals(effective, value, StringComparison.OrdinalIgnoreCase)) continue;
            var target = TargetOf(key);
            if (root is not null && !rewritten && !target.Values.Keys.Any(k => k.StartsWith(root + ":", StringComparison.OrdinalIgnoreCase)))
                foreach (var (k, v) in current.Values.Where(kv => kv.Key.StartsWith(root + ":", StringComparison.OrdinalIgnoreCase)))
                    target.Values[k] = v;
            target.EmptyArrays.Remove(root ?? key);
            target.Values[key] = value!;
            written.Add(key);
        }
        written.AddRange(cleared);

        if (written.Count == 0) return new SavePlan([], [], [], next, nextMachine);

        var writesMachine = written.Any(IsMachineScoped);
        // Old per-user Sources and Sftp values are dropped from the file together with any other save to it.
        var writesUser = written.Any(k => !IsMachineScoped(k)) || layers.IgnoredUserKeys.Count > 0;
        var candidate = Evaluate(layers with { Machine = nextMachine, User = next, IgnoredUserKeys = [] }, headless: false, machineWritable);
        return new SavePlan(candidate.Errors, candidate.Warnings, written, next, nextMachine, writesUser, writesMachine);
    }

    /// <summary>The documented default of a scalar key, as text; null for lists, unknown keys and keys without a default.</summary>
    internal static string? DefaultText(string key)
    {
        object? node = new AppConfig();
        foreach (var segment in key.Split(':'))
        {
            var property = node?.GetType().GetProperty(segment, System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.IgnoreCase);
            if (property is null) return null;
            node = property.GetValue(node);
        }
        return node switch
        {
            null => null,
            bool b => b ? "true" : "false",
            string or Enum or int or long => Convert.ToString(node, System.Globalization.CultureInfo.InvariantCulture),
            _ => null,
        };
    }

    private static void RemoveUnder(FlatSettings flat, string key)
    {
        var under = key + ":";
        foreach (var k in flat.Values.Keys.Where(k => k.Equals(key, StringComparison.OrdinalIgnoreCase) || k.StartsWith(under, StringComparison.OrdinalIgnoreCase)).ToList())
            flat.Values.Remove(k);
        flat.EmptyArrays.RemoveWhere(k => k.Equals(key, StringComparison.OrdinalIgnoreCase) || k.StartsWith(under, StringComparison.OrdinalIgnoreCase));
    }

    private static ConfigLayer LayerOf(MergedSettings merged, string key)
    {
        if (merged.Layers.TryGetValue(key, out var exact)) return exact;
        foreach (var prefix in new[] { key, FlatSettings.ArrayRootOf(key) })
            if (prefix is not null)
                foreach (var (k, layer) in merged.Layers)
                    if (k.StartsWith(prefix + ":", StringComparison.OrdinalIgnoreCase)) return layer;
        return ConfigLayer.Default;
    }

    private static void WriteAtomically(string path, string content)
    {
        var dir = Path.GetDirectoryName(Path.GetFullPath(path))!;
        Directory.CreateDirectory(dir);
        var temp = Path.Combine(dir, $".{Path.GetFileName(path)}.{Guid.NewGuid():N}.tmp");
        try
        {
            File.WriteAllText(temp, content);
            File.Move(temp, path, overwrite: true);
        }
        finally
        {
            if (File.Exists(temp)) File.Delete(temp);
        }
    }

    /// <summary>The Secrets in the environment. Hand them to the code that connects; never log them.</summary>
    /// <summary>Whether and where each Secret is set, for the Settings screen. Never the values.</summary>
    public SecretStatus LoadSecretStatus(IEnumerable<SourceConfig> sources) => LoadSecrets().Status(sources);

    /// <summary>Stores a Secret in the account's Secret Store. Returns why it could not, or null.</summary>
    public string? SetSecret(string name, string value) => WithStore(store => store.Set(name, value));

    /// <summary>Removes a Secret from the account's Secret Store. Returns why it could not, or null.</summary>
    public string? ClearSecret(string name) => WithStore(store => store.Clear(name));

    private string? WithStore(Action<SecretStore> action)
    {
        if (locations.SecretStorePath is null || locations.Identity is null) return "The Secret Store is not configured.";
        try
        {
            using var store = SecretStore.Open(locations.SecretStorePath, locations.Identity);
            action(store);
            return null;
        }
        catch (SecretStoreUnavailableException e)
        {
            return e.Message;
        }
    }

    public Secrets LoadSecrets()
    {
        if (locations.SecretStorePath is null || locations.Identity is null)
            return Secrets.FromEnvironment(locations.Environment);
        if (string.IsNullOrWhiteSpace(locations.Identity.MachineId))
            return Secrets.FromEnvironmentWithoutStore(locations.Environment, SecretStore.NoMachineIdentifierMessage);
        if (!File.Exists(locations.SecretStorePath))
            return Secrets.FromEnvironment(locations.Environment);
        try
        {
            using var store = SecretStore.Open(locations.SecretStorePath, locations.Identity);
            return Secrets.FromEnvironmentAndStore(locations.Environment, store.List().Select(s => (s.Name, store.Get(s.Name))));
        }
        catch (SecretStoreUnavailableException e)
        {
            return Secrets.FromEnvironmentWithoutStore(locations.Environment, e.Message);
        }
    }

    // ---- layers ----

    internal sealed record Layers(FlatSettings Machine, FlatSettings User, FlatSettings Environment, FlatSettings Cli)
    {
        /// <summary>Keys (or list roots) found in User Overrides that belong in Machine Config; they were left out of <see cref="User"/>.</summary>
        public IReadOnlyList<string> IgnoredUserKeys { get; init; } = [];
    }

    internal Layers? ReadLayers(CliOptions cli, out List<ConfigError> errors, bool machineRequired = true)
    {
        errors = [];
        var machine = ReadFile(locations.MachineConfigPath, "Machine Config", required: machineRequired, errors);
        var user = ReadFile(locations.UserOverridesPath, "User Overrides", required: false, errors);
        if (errors.Count > 0) return null;

        var ignored = new List<string>();
        foreach (var key in user!.Values.Keys.Where(IsMachineScoped).ToList())
        {
            user.Values.Remove(key);
            var root = FlatSettings.ArrayRootOf(key) ?? key;
            if (!ignored.Contains(root, StringComparer.OrdinalIgnoreCase)) ignored.Add(root);
        }
        foreach (var empty in user.EmptyArrays.Where(IsMachineScoped).ToList())
        {
            user.EmptyArrays.Remove(empty);
            if (!ignored.Contains(empty, StringComparer.OrdinalIgnoreCase)) ignored.Add(empty);
        }

        var env = new FlatSettings();
        foreach (var (name, value) in locations.Environment)
        {
            if (value is null || !name.StartsWith("MIRES_", StringComparison.OrdinalIgnoreCase)) continue;
            var rest = name["MIRES_".Length..];
            if (rest.Equals("DATA_DIR", StringComparison.OrdinalIgnoreCase)) env.Values["State:Path"] = value;
            else if (rest.Contains("__") && !Secrets.IsSecretName(name)) env.Values[rest.Replace("__", ":")] = value;
        }

        var cliLayer = new FlatSettings();
        foreach (var (k, v) in cli.ConfigOverrides) cliLayer.Values[k] = v;
        return new Layers(machine!, user, env, cliLayer) { IgnoredUserKeys = ignored };
    }

    private static FlatSettings? ReadFile(string path, string what, bool required, List<ConfigError> errors)
    {
        if (!File.Exists(path))
        {
            if (required) errors.Add(new(null, $"{what} not found: {path}"));
            return new FlatSettings();
        }

        try
        {
            var flat = FlatSettings.FromJson(File.ReadAllText(path));
            if (flat.Values.Remove("ConfigVersion", out var version) && (!int.TryParse(version, out var v) || v > ConfigVersion))
                errors.Add(new("ConfigVersion", $"{what} {path} has version {version}; this program understands up to {ConfigVersion}."));
            return flat;
        }
        catch (Exception e) when (e is JsonException or IOException or UnauthorizedAccessException)
        {
            errors.Add(new(null, $"{what} {path} cannot be read: {e.Message}"));
            return null;
        }
    }

    internal sealed record MergedSettings(Dictionary<string, string> Values, Dictionary<string, ConfigLayer> Layers);

    internal static MergedSettings Merge(Layers layers)
    {
        var values = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        var origin = new Dictionary<string, ConfigLayer>(StringComparer.OrdinalIgnoreCase);

        void Apply(FlatSettings layer, ConfigLayer id)
        {
            foreach (var root in layer.ArrayRoots())
            {
                var under = root + ":";
                foreach (var k in values.Keys.Where(k => k.StartsWith(under, StringComparison.OrdinalIgnoreCase)).ToList())
                {
                    values.Remove(k);
                    origin.Remove(k);
                }
            }
            foreach (var (k, v) in layer.Values)
            {
                values[k] = v;
                origin[k] = id;
            }
            foreach (var empty in layer.EmptyArrays)
                origin[empty] = id;
        }

        Apply(layers.Machine, ConfigLayer.Machine);
        Apply(layers.User, ConfigLayer.User);
        Apply(layers.Environment, ConfigLayer.Environment);
        Apply(layers.Cli, ConfigLayer.Cli);
        return new MergedSettings(values, origin);
    }

    // ---- binding ----

    private static readonly (Regex Key, Type Enum)[] EnumKeys =
    [
        (new(@"^Sftp:AuthMethod$", RegexOptions.IgnoreCase), typeof(AuthMethod)),
        (new(@"^Sftp:RemoteAccess$", RegexOptions.IgnoreCase), typeof(RemoteAccess)),
        (new(@"^Sftp:UploadStrategy$", RegexOptions.IgnoreCase), typeof(UploadStrategy)),
        (new(@"^Sources:\d+:Type$", RegexOptions.IgnoreCase), typeof(SourceType)),
        (new(@"^(Sources:\d+:ArchiveRules|Archive:Rules):\d+:Grouping$", RegexOptions.IgnoreCase), typeof(ArchiveGrouping)),
        (new(@"^Upload:Verify(AfterUpload|Remote)$", RegexOptions.IgnoreCase), typeof(VerificationLevel)),
        (new(@"^Sources:\d+:AfterUpload:On(Success|Failure):Action$", RegexOptions.IgnoreCase), typeof(MoveAction)),
        (new(@"^Report:Format$", RegexOptions.IgnoreCase), typeof(ReportFormat)),
        (new(@"^Ui:Theme$", RegexOptions.IgnoreCase), typeof(UiTheme)),
        (new(@"^(Ui:LogLevel|Logging:Level)$", RegexOptions.IgnoreCase), typeof(LogLevelSetting)),
    ];

    private static readonly Regex SecretLikeKey = new(@"(^|:)(Password|KeyPassphrase|AccessKey|SecretKey)$", RegexOptions.IgnoreCase);

    private static AppConfig? Bind(Dictionary<string, string> values, List<ConfigError> errors)
    {
        var before = errors.Count;
        foreach (var (key, value) in values)
            foreach (var (pattern, enumType) in EnumKeys)
                if (pattern.IsMatch(key) && (!Enum.TryParse(enumType, value, ignoreCase: true, out var parsed) || !Enum.IsDefined(enumType, parsed!) || int.TryParse(value, out _)))
                    errors.Add(new(key, $"'{value}' is not one of {string.Join(", ", Enum.GetNames(enumType))}."));
        if (errors.Count > before) return null;

        try
        {
            var root = new ConfigurationBuilder().AddInMemoryCollection(values!).Build();
            var config = root.Get<AppConfig>() ?? new AppConfig();
            return config with { Sftp = config.Sftp with { HostKeyFingerprint = NormaliseFingerprint(config.Sftp.HostKeyFingerprint) } };
        }
        catch (InvalidOperationException e)
        {
            errors.Add(new(null, e.InnerException?.Message is { } inner ? $"{e.Message} {inner}" : e.Message));
            return null;
        }
    }

    internal static string? NormaliseFingerprint(string? fingerprint)
    {
        if (string.IsNullOrWhiteSpace(fingerprint)) return fingerprint;
        var f = fingerprint.Trim();
        foreach (var prefix in new[] { "SHA256:", "MD5:" })
            if (f.StartsWith(prefix, StringComparison.OrdinalIgnoreCase)) return f[prefix.Length..];
        return f;
    }

    internal static bool IsDirectoryWritable(string directory)
    {
        try
        {
            var probe = Path.Combine(directory, ".mires-write-probe-" + Guid.NewGuid().ToString("N"));
            using (File.Create(probe)) { }
            File.Delete(probe);
            return true;
        }
        catch (Exception e) when (e is UnauthorizedAccessException or IOException)
        {
            return false;
        }
    }
}

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

    public bool Succeeded => Errors.Count == 0;

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
        return new SettingInfo(ConfigLayer.Default, false);
    }
}

public sealed record ConfigurationLocations(string MachineConfigPath, string UserOverridesPath, IReadOnlyDictionary<string, string?> Environment)
{
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
            env);
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
/// An array is replaced whole by the highest layer that defines it. Secrets come only from environment variables
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

        var merged = Merge(layers);
        var keys = merged.Layers.ToDictionary(
            kv => kv.Key,
            kv => new SettingInfo(kv.Value, kv.Value is ConfigLayer.Environment or ConfigLayer.Cli || (kv.Value == ConfigLayer.Machine && !machineWritable)),
            StringComparer.OrdinalIgnoreCase);

        var config = Bind(merged.Values, errors);
        var warnings = new List<ConfigError>();
        foreach (var (layer, file) in new[] { ("Machine Config", layers.Machine), ("User Overrides", layers.User) })
            foreach (var key in file.Values.Keys.Where(k => SecretLikeKey.IsMatch(k)))
                warnings.Add(new(key, $"{layer} must not hold a Secret; the value is ignored. Set it in an environment variable."));
        if (config is not null)
            ConfigValidator.Validate(config, headless, errors, warnings);

        return new LoadResult
        {
            Config = errors.Count == 0 ? config : null,
            Errors = errors,
            Warnings = warnings,
            MachineConfigWritable = machineWritable,
            Keys = keys,
            Secrets = LoadSecrets().Status(config?.Sources ?? []),
        };
    }

    /// <summary>The Secrets in the environment. Hand them to the code that connects; never log them.</summary>
    public Secrets LoadSecrets() => Secrets.FromEnvironment(locations.Environment);

    // ---- layers ----

    internal sealed record Layers(FlatSettings Machine, FlatSettings User, FlatSettings Environment, FlatSettings Cli);

    internal Layers? ReadLayers(CliOptions cli, out List<ConfigError> errors)
    {
        errors = [];
        var machine = ReadFile(locations.MachineConfigPath, "Machine Config", required: true, errors);
        var user = ReadFile(locations.UserOverridesPath, "User Overrides", required: false, errors);
        if (errors.Count > 0) return null;

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
        return new Layers(machine!, user!, env, cliLayer);
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

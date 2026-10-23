using System.Text.RegularExpressions;

namespace MiresSftpUploader.Core;

/// <summary>Reports every problem at once, as <see cref="ConfigError"/> keyed by the configuration key path.</summary>
internal sealed partial class ConfigValidator
{
    private readonly AppConfig _config;
    private readonly bool _headless;
    private readonly List<ConfigError> _errors;
    private readonly List<ConfigError> _warnings;

    private ConfigValidator(AppConfig config, bool headless, List<ConfigError> errors, List<ConfigError> warnings)
    {
        _config = config;
        _headless = headless;
        _errors = errors;
        _warnings = warnings;
    }

    public static void Validate(AppConfig config, bool headless, List<ConfigError> errors, List<ConfigError> warnings) =>
        new ConfigValidator(config, headless, errors, warnings).Run();

    private void Error(string key, string message) => _errors.Add(new(key, message));

    private void Run()
    {
        Sftp();
        Sources();
        IgnorePatterns(_config.Ignore.Patterns, "Ignore:Patterns");
        ArchiveRules(_config.Archive.Rules, "Archive:Rules");
        Range("Archive:MaxParallelBuilds", _config.Archive.MaxParallelBuilds, 1, 16);
        if (_config.Archive.MinFreeSpaceBytes < 0) Error("Archive:MinFreeSpaceBytes", "must not be negative.");
        if (_config.Archive.WarnAboveBytes < 0) Error("Archive:WarnAboveBytes", "must not be negative.");
        Range("Scan:MinFileAgeSeconds", _config.Scan.MinFileAgeSeconds, 0, int.MaxValue);
        Manifest();
        Range("Upload:MaxParallelUploads", _config.Upload.MaxParallelUploads, 1, 16);
        Range("Upload:VerifyTimeoutSeconds", _config.Upload.VerifyTimeoutSeconds, 1, 7 * 24 * 3600);
        if (!VerifyCommand.IsValidTemplate(_config.Upload.VerifyCommand))
            Error("Upload:VerifyCommand", "must contain the {path} placeholder.");
        if (_config.Sftp.RemoteAccess == RemoteAccess.WriteOnly)
        {
            if (_config.Upload.VerifyAfterUpload != VerificationLevel.Off)
                Error("Upload:VerifyAfterUpload", "Verification reads from the server and conflicts with RemoteAccess WriteOnly.");
            if (_config.Upload.VerifyRemote != VerificationLevel.Off)
                Error("Upload:VerifyRemote", "Verification reads from the server and conflicts with RemoteAccess WriteOnly.");
        }
        Range("Retry:MaxAttempts", _config.Retry.MaxAttempts, 0, 10);
        Range("Retry:BaseDelaySeconds", _config.Retry.BaseDelaySeconds, 0, 3600);
        Range("Retry:MaxDelaySeconds", _config.Retry.MaxDelaySeconds, 0, 3600);
        if (_config.Retry.BaseDelaySeconds > _config.Retry.MaxDelaySeconds)
            Error("Retry:BaseDelaySeconds", "must not exceed Retry:MaxDelaySeconds.");
        State();
        Range("Logging:RetainDays", _config.Logging.RetainDays, 0, 3650);
    }

    private void Sftp()
    {
        var s = _config.Sftp;
        if (string.IsNullOrWhiteSpace(s.Host)) Error("Sftp:Host", "is required.");
        if (string.IsNullOrWhiteSpace(s.Username)) Error("Sftp:Username", "is required.");
        if (string.IsNullOrWhiteSpace(s.HostKeyFingerprint)) Error("Sftp:HostKeyFingerprint", "is required: the server's host key must be pinned.");
        if (s.AuthMethod == AuthMethod.PrivateKey && string.IsNullOrWhiteSpace(s.PrivateKeyPath))
            Error("Sftp:PrivateKeyPath", "is required when AuthMethod is PrivateKey.");
        Range("Sftp:Port", s.Port, 1, 65535);
        Range("Sftp:ConnectTimeoutSeconds", s.ConnectTimeoutSeconds, 1, 3600);
        Range("Sftp:KeepAliveSeconds", s.KeepAliveSeconds, 0, 3600);
        RemotePath("Sftp:RemoteRoot", s.RemoteRoot);
    }

    private void Sources()
    {
        var sources = _config.Sources;
        if (!sources.Any(s => s.Enabled))
            Error("Sources", "at least one enabled Source is required.");

        var seen = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
        var s3Names = new Dictionary<string, string>(StringComparer.Ordinal);
        for (var i = 0; i < sources.Count; i++)
        {
            var s = sources[i];
            var p = $"Sources:{i}";

            if (string.IsNullOrWhiteSpace(s.Name)) Error($"{p}:Name", "is required.");
            else if (!FilenameSafe().IsMatch(s.Name)) Error($"{p}:Name", $"'{s.Name}' is not filename-safe: use letters, digits, '.', '_' and '-', not starting with '.'.");
            else if (!seen.TryAdd(s.Name, i)) Error($"{p}:Name", $"'{s.Name}' is not unique (also Sources:{seen[s.Name]}).");
            else if (s.Type == SourceType.S3)
            {
                var variable = Secrets.NormaliseSourceName(s.Name);
                if (s3Names.TryGetValue(variable, out var other))
                    Error($"{p}:Name", $"'{s.Name}' and '{other}' give the same secret variable name MIRES_S3_{variable}_*.");
                else s3Names[variable] = s.Name;
            }

            if (s.RemotePath is not null) RemotePath($"{p}:RemotePath", s.RemotePath);
            IgnorePatterns(s.Ignore.Patterns, $"{p}:Ignore:Patterns");
            ArchiveRules(s.ArchiveRules, $"{p}:ArchiveRules");
            if (s.Scan.MinFileAgeSeconds is < 0) Error($"{p}:Scan:MinFileAgeSeconds", "must be 0 or more.");

            if (s.Type == SourceType.Directory)
            {
                if (string.IsNullOrWhiteSpace(s.Path)) Error($"{p}:Path", "is required for a Directory Source.");
                else if (s.Enabled && !Directory.Exists(s.Path))
                {
                    var message = new ConfigError($"{p}:Path", $"directory '{s.Path}' does not exist.");
                    (_headless ? _errors : _warnings).Add(message);
                }
            }
            else
            {
                if (string.IsNullOrWhiteSpace(s.Endpoint)) Error($"{p}:Endpoint", "is required for an S3 Source.");
                if (string.IsNullOrWhiteSpace(s.Bucket)) Error($"{p}:Bucket", "is required for an S3 Source.");
            }

            MoveTarget(s, s.AfterUpload.OnSuccess, $"{p}:AfterUpload:OnSuccess");
            MoveTarget(s, s.AfterUpload.OnFailure, $"{p}:AfterUpload:OnFailure");
        }
    }

    private void MoveTarget(SourceConfig source, MoveTargetConfig target, string p)
    {
        if (target.Action != MoveAction.Move) return;

        if (source.Type == SourceType.Directory)
        {
            if (string.IsNullOrWhiteSpace(target.Path)) { Error($"{p}:Path", "is required when Action is Move."); return; }
            if (!string.IsNullOrWhiteSpace(source.Path) && DirectoriesOverlap(source.Path, target.Path))
                Error($"{p}:Path", $"'{target.Path}' overlaps the Source path '{source.Path}'.");
        }
        else
        {
            if (string.IsNullOrWhiteSpace(target.Bucket)) { Error($"{p}:Bucket", "is required when Action is Move."); return; }
            if (string.Equals(target.Bucket, source.Bucket, StringComparison.Ordinal) && PrefixesOverlap(source.Prefix, target.Prefix))
                Error($"{p}:Prefix", $"'{target.Prefix}' overlaps the Source prefix '{source.Prefix}'.");
        }
    }

    private static bool DirectoriesOverlap(string a, string b)
    {
        static string Norm(string p) => Path.GetFullPath(p).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        var (x, y) = (Norm(a), Norm(b));
        var sep = Path.DirectorySeparatorChar;
        return x.Equals(y, StringComparison.OrdinalIgnoreCase)
            || x.StartsWith(y + sep, StringComparison.OrdinalIgnoreCase)
            || y.StartsWith(x + sep, StringComparison.OrdinalIgnoreCase);
    }

    private static bool PrefixesOverlap(string? a, string? b)
    {
        static string Norm(string? p) => string.IsNullOrEmpty(p) ? "" : p.TrimStart('/').TrimEnd('/') + "/";
        var (x, y) = (Norm(a), Norm(b));
        return x.StartsWith(y, StringComparison.Ordinal) || y.StartsWith(x, StringComparison.Ordinal);
    }

    private void IgnorePatterns(IReadOnlyList<string> patterns, string key)
    {
        for (var i = 0; i < patterns.Count; i++) CompileCheck(patterns[i], $"{key}:{i}");
    }

    private void ArchiveRules(IReadOnlyList<ArchiveRuleConfig> rules, string key)
    {
        var names = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        for (var i = 0; i < rules.Count; i++)
        {
            var r = rules[i];
            var p = $"{key}:{i}";
            if (string.IsNullOrWhiteSpace(r.Name)) Error($"{p}:Name", "is required.");
            else if (!names.Add(r.Name)) Error($"{p}:Name", $"'{r.Name}' is not unique among the Archive Rules.");
            if (string.IsNullOrWhiteSpace(r.Pattern)) Error($"{p}:Pattern", "is required.");
            else CompileCheck(r.Pattern, $"{p}:Pattern");
            Range($"{p}:MinFiles", r.MinFiles, 1, int.MaxValue);
            foreach (Match m in TemplateToken().Matches(r.ArchiveName))
                if (m.Value is not ("{rule}" or "{dir}" or "{date}"))
                    Error($"{p}:ArchiveName", $"unknown placeholder {m.Value}; use {{rule}}, {{dir}} or {{date}}.");
        }
    }

    private void CompileCheck(string pattern, string key)
    {
        try { _ = new Regex(pattern, RegexOptions.IgnoreCase | RegexOptions.CultureInvariant); }
        catch (ArgumentException e) { Error(key, $"is not a valid regular expression: {e.Message}"); }
    }

    private void Manifest()
    {
        var m = _config.Manifest;
        PlainFileName("Manifest:JsonName", m.JsonName);
        PlainFileName("Manifest:FlatName", m.FlatName);
        if (string.IsNullOrWhiteSpace(m.InProgressSuffix)) Error("Manifest:InProgressSuffix", "is required.");

        var taken = new HashSet<string>(StringComparer.OrdinalIgnoreCase) { m.JsonName };
        if (!taken.Add(m.FlatName)) Error("Manifest:FlatName", "collides with Manifest:JsonName.");
        foreach (var (key, name) in new[] { ("Manifest:JsonName", m.JsonName), ("Manifest:FlatName", m.FlatName) })
            if (!string.IsNullOrEmpty(m.InProgressSuffix) && taken.Contains(name + m.InProgressSuffix))
                Error(key, "collides with a name made by Manifest:InProgressSuffix.");
    }

    private void PlainFileName(string key, string name)
    {
        if (string.IsNullOrWhiteSpace(name) || name.AsSpan().IndexOfAny('/', '\\') >= 0 || name is "." or "..")
            Error(key, "must be a plain file name without directories.");
    }

    private void State()
    {
        var s = _config.State;
        Range("State:RunFilesRetentionDays", s.RunFilesRetentionDays, 1, 36500);
        Range("State:MissingRetentionDays", s.MissingRetentionDays, 1, 36500);
        Range("State:HeartbeatSeconds", s.HeartbeatSeconds, 1, 3600);
        Range("State:StaleAfterSeconds", s.StaleAfterSeconds, 1, 86400);
        Range("State:CancelPollSeconds", s.CancelPollSeconds, 1, 3600);
        if (s.StaleAfterSeconds <= s.HeartbeatSeconds)
            Error("State:StaleAfterSeconds", "must be longer than State:HeartbeatSeconds.");
    }

    private void RemotePath(string key, string path)
    {
        if (string.IsNullOrEmpty(path) || path[0] != '/' || path.Contains('\\') || path.Split('/').Contains(".."))
            Error(key, $"'{path}' must be an absolute POSIX path (starting with '/', using '/', without '..').");
    }

    private void Range(string key, int value, int min, int max)
    {
        if (value < min || value > max)
            Error(key, max == int.MaxValue ? $"{value} is out of range; must be at least {min}." : $"{value} is out of range {min} to {max}.");
    }

    [GeneratedRegex(@"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")]
    private static partial Regex FilenameSafeCore();
    private static Regex FilenameSafe() => FilenameSafeCore();

    [GeneratedRegex(@"\{[^}]*\}")]
    private static partial Regex TemplateToken();
}

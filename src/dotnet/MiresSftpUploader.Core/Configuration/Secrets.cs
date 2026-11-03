using System.Text.RegularExpressions;

namespace MiresSftpUploader.Core;

public sealed record S3KeyStatus(bool AccessKeySet, bool SecretKeySet);

/// <summary>Where a Secret's effective value comes from.</summary>
public enum SecretOrigin { NotSet, Environment, Stored, Unreadable }

/// <summary>What the UI may know about Secrets: whether each is set and where it comes from, never the value.</summary>
public sealed record SecretStatus(bool SftpPassword, bool SftpKeyPassphrase, IReadOnlyDictionary<string, S3KeyStatus> S3)
{
    public static SecretStatus None { get; } = new(false, false, new Dictionary<string, S3KeyStatus>());

    /// <summary>The origin of each Secret by its Secret Store name (<c>sftp-password</c>, <c>s3-secret-key:&lt;Source&gt;</c>).</summary>
    public IReadOnlyDictionary<string, SecretOrigin> Origins { get; init; } = new Dictionary<string, SecretOrigin>(StringComparer.OrdinalIgnoreCase);

    /// <summary>Why the Secret Store cannot be used on this machine; null when it can, or is not configured.</summary>
    public string? StoreProblem { get; init; }

    public SecretOrigin OriginOf(string name) => Origins.TryGetValue(name, out var origin) ? origin : SecretOrigin.NotSet;
}

public sealed record S3Credentials(string AccessKey, string SecretKey)
{
    public override string ToString() => "S3Credentials { redacted }";
}

/// <summary>
/// A snapshot of the Secrets in the environment. Read once at the start of a Run. Never part of <see cref="AppConfig"/>,
/// never saved, and it prints as redacted.
/// </summary>
public sealed class Secrets
{
    public const string SftpPasswordVariable = "MIRES_SFTP_PASSWORD";
    public const string SftpKeyPassphraseVariable = "MIRES_SFTP_KEY_PASSPHRASE";

    private static readonly Regex S3VariablePattern = new(@"^MIRES_S3_.+_(ACCESS|SECRET)_KEY$", RegexOptions.CultureInvariant);

    public const string SftpPasswordName = "sftp-password";
    public const string SftpKeyPassphraseName = "sftp-key-passphrase";

    private readonly IReadOnlyDictionary<string, string?> _environment;
    private readonly IReadOnlyDictionary<string, SecretLookup> _stored;
    private readonly string? _storeProblem;

    private Secrets(IReadOnlyDictionary<string, string?> environment, IReadOnlyDictionary<string, SecretLookup> stored, string? storeProblem = null)
    {
        _environment = environment;
        _stored = stored;
        _storeProblem = storeProblem;
    }

    /// <summary>The environment alone, because the Secret Store cannot be used; <paramref name="problem"/> says why.</summary>
    internal static Secrets FromEnvironmentWithoutStore(IReadOnlyDictionary<string, string?> environment, string problem) =>
        new(environment, new Dictionary<string, SecretLookup>(), problem);

    internal static Secrets FromEnvironment(IReadOnlyDictionary<string, string?> environment) =>
        new(environment, new Dictionary<string, SecretLookup>());

    /// <summary>The environment, with the Secret Store as the fallback for any Secret the environment does not supply.</summary>
    internal static Secrets FromEnvironmentAndStore(IReadOnlyDictionary<string, string?> environment, IEnumerable<(string Name, SecretLookup Lookup)> stored)
    {
        var byName = new Dictionary<string, SecretLookup>(StringComparer.OrdinalIgnoreCase);
        foreach (var (name, lookup) in stored) byName.TryAdd(name, lookup);
        return new(environment, byName);
    }

    public string? SftpPassword => Get(SftpPasswordVariable, SftpPasswordName);
    public string? SftpKeyPassphrase => Get(SftpKeyPassphraseVariable, SftpKeyPassphraseName);

    public S3Credentials? S3(string sourceName)
    {
        var access = Get(S3Variable(sourceName, "ACCESS_KEY"), S3Name(sourceName, "access-key"));
        var secret = Get(S3Variable(sourceName, "SECRET_KEY"), S3Name(sourceName, "secret-key"));
        return access is null || secret is null ? null : new S3Credentials(access, secret);
    }

    /// <summary>True when the Secret is in the Secret Store but cannot be decrypted here, and the environment does not supply it.</summary>
    public bool IsUnreadable(string storeName, string variable) =>
        !(_environment.TryGetValue(variable, out var v) && !string.IsNullOrEmpty(v))
        && _stored.TryGetValue(storeName, out var lookup) && lookup.State == SecretState.Unreadable;

    public bool SftpPasswordUnreadable => IsUnreadable(SftpPasswordName, SftpPasswordVariable);

    public static string S3Name(string sourceName, string kind) => $"s3-{kind}:{sourceName}";

    /// <summary>The environment variable part for a Source name: uppercased, every non-alphanumeric character becomes <c>_</c>.</summary>
    public static string NormaliseSourceName(string name) =>
        string.Concat(name.ToUpperInvariant().Select(c => char.IsAsciiLetterOrDigit(c) ? c : '_'));

    internal static bool IsSecretName(string variable) =>
        variable is SftpPasswordVariable or SftpKeyPassphraseVariable || S3VariablePattern.IsMatch(variable);

    /// <summary>Every Secret value in the snapshot. For the <see cref="Redactor"/> only.</summary>
    internal IEnumerable<string> Values() =>
        _environment.Where(kv => IsSecretName(kv.Key) && !string.IsNullOrEmpty(kv.Value)).Select(kv => kv.Value!)
            .Concat(_stored.Values.Where(l => l.State == SecretState.Stored && !string.IsNullOrEmpty(l.Value)).Select(l => l.Value!));

    internal SecretStatus Status(IEnumerable<SourceConfig> sources)
    {
        var s3 = new Dictionary<string, S3KeyStatus>(StringComparer.OrdinalIgnoreCase);
        foreach (var s in sources.Where(s => s.Type == SourceType.S3 && !string.IsNullOrEmpty(s.Name)))
            s3[s.Name!] = new S3KeyStatus(
                Get(S3Variable(s.Name!, "ACCESS_KEY"), S3Name(s.Name!, "access-key")) is not null,
                Get(S3Variable(s.Name!, "SECRET_KEY"), S3Name(s.Name!, "secret-key")) is not null);
        var origins = new Dictionary<string, SecretOrigin>(StringComparer.OrdinalIgnoreCase)
        {
            [SftpPasswordName] = OriginOf(SftpPasswordVariable, SftpPasswordName),
            [SftpKeyPassphraseName] = OriginOf(SftpKeyPassphraseVariable, SftpKeyPassphraseName),
        };
        foreach (var s in sources.Where(s => s.Type == SourceType.S3 && !string.IsNullOrEmpty(s.Name)))
        {
            origins[S3Name(s.Name!, "access-key")] = OriginOf(S3Variable(s.Name!, "ACCESS_KEY"), S3Name(s.Name!, "access-key"));
            origins[S3Name(s.Name!, "secret-key")] = OriginOf(S3Variable(s.Name!, "SECRET_KEY"), S3Name(s.Name!, "secret-key"));
        }
        return new SecretStatus(SftpPassword is not null, SftpKeyPassphrase is not null, s3) { Origins = origins, StoreProblem = _storeProblem };
    }

    private SecretOrigin OriginOf(string variable, string storeName) =>
        _environment.TryGetValue(variable, out var v) && !string.IsNullOrEmpty(v) ? SecretOrigin.Environment
        : _stored.TryGetValue(storeName, out var l) ? l.State switch
        {
            SecretState.Stored => SecretOrigin.Stored,
            SecretState.Unreadable => SecretOrigin.Unreadable,
            _ => SecretOrigin.NotSet,
        }
        : SecretOrigin.NotSet;

    public override string ToString() => "Secrets { redacted }";

    private static string S3Variable(string sourceName, string suffix) => $"MIRES_S3_{NormaliseSourceName(sourceName)}_{suffix}";

    private string? Get(string variable, string storeName) =>
        _environment.TryGetValue(variable, out var v) && !string.IsNullOrEmpty(v) ? v
        : _stored.TryGetValue(storeName, out var l) && l.State == SecretState.Stored ? l.Value
        : null;
}

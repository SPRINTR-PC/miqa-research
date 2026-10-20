using System.Text.RegularExpressions;

namespace MiresSftpUploader.Core;

public sealed record S3KeyStatus(bool AccessKeySet, bool SecretKeySet);

/// <summary>What the UI may know about Secrets: only whether each is set.</summary>
public sealed record SecretStatus(bool SftpPassword, bool SftpKeyPassphrase, IReadOnlyDictionary<string, S3KeyStatus> S3)
{
    public static SecretStatus None { get; } = new(false, false, new Dictionary<string, S3KeyStatus>());
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

    private readonly IReadOnlyDictionary<string, string?> _environment;

    private Secrets(IReadOnlyDictionary<string, string?> environment) => _environment = environment;

    internal static Secrets FromEnvironment(IReadOnlyDictionary<string, string?> environment) => new(environment);

    public string? SftpPassword => Get(SftpPasswordVariable);
    public string? SftpKeyPassphrase => Get(SftpKeyPassphraseVariable);

    public S3Credentials? S3(string sourceName)
    {
        var access = Get(S3Variable(sourceName, "ACCESS_KEY"));
        var secret = Get(S3Variable(sourceName, "SECRET_KEY"));
        return access is null || secret is null ? null : new S3Credentials(access, secret);
    }

    /// <summary>The environment variable part for a Source name: uppercased, every non-alphanumeric character becomes <c>_</c>.</summary>
    public static string NormaliseSourceName(string name) =>
        string.Concat(name.ToUpperInvariant().Select(c => char.IsAsciiLetterOrDigit(c) ? c : '_'));

    internal static bool IsSecretName(string variable) =>
        variable is SftpPasswordVariable or SftpKeyPassphraseVariable || S3VariablePattern.IsMatch(variable);

    internal SecretStatus Status(IEnumerable<SourceConfig> sources)
    {
        var s3 = new Dictionary<string, S3KeyStatus>(StringComparer.OrdinalIgnoreCase);
        foreach (var s in sources.Where(s => s.Type == SourceType.S3 && !string.IsNullOrEmpty(s.Name)))
            s3[s.Name!] = new S3KeyStatus(Get(S3Variable(s.Name!, "ACCESS_KEY")) is not null, Get(S3Variable(s.Name!, "SECRET_KEY")) is not null);
        return new SecretStatus(SftpPassword is not null, SftpKeyPassphrase is not null, s3);
    }

    public override string ToString() => "Secrets { redacted }";

    private static string S3Variable(string sourceName, string suffix) => $"MIRES_S3_{NormaliseSourceName(sourceName)}_{suffix}";

    private string? Get(string variable) =>
        _environment.TryGetValue(variable, out var v) && !string.IsNullOrEmpty(v) ? v : null;
}

using System.Text.RegularExpressions;

namespace MiresSftpUploader.Core;

/// <summary>The Verification command run on the server for the Hash level: a template, a shell-quoted path, a parsed SHA-256.</summary>
public static partial class VerifyCommand
{
    public const string PathPlaceholder = "{path}";

    public static bool IsValidTemplate(string template) => template.Contains(PathPlaceholder, StringComparison.Ordinal);

    /// <summary>Replaces <c>{path}</c> with the single-quoted path.</summary>
    public static string Build(string template, string remotePath) =>
        template.Replace(PathPlaceholder, "'" + remotePath.Replace("'", "'\\''") + "'", StringComparison.Ordinal);

    /// <summary>The first 64 hex characters of the output, lower-cased; null when the output holds none.</summary>
    public static string? ParseHash(string output)
    {
        var match = HexHash().Match(output);
        return match.Success ? match.Value.ToLowerInvariant() : null;
    }

    [GeneratedRegex("(?<![0-9a-fA-F])[0-9a-fA-F]{64}(?![0-9a-fA-F])")]
    private static partial Regex HexHash();
}

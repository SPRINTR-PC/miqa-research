using System.Text.RegularExpressions;

namespace MiresSftpUploader.Core;

/// <summary>
/// The Ignore Rules in force for one Source: the built-in junk patterns (unless switched off),
/// exact relative paths, and regular expressions matched against the forward-slash relative path.
/// </summary>
internal sealed class IgnoreRules
{
    internal static readonly TimeSpan PatternTimeout = TimeSpan.FromSeconds(1);

    private static readonly Regex BuiltIn = new(
        @"(^|/)(\.DS_Store|Thumbs\.db|desktop\.ini|\._[^/]*)$",
        RegexOptions.IgnoreCase | RegexOptions.CultureInvariant, PatternTimeout);

    private readonly bool _useDefaults;
    private readonly HashSet<string> _files;
    private readonly List<Regex> _patterns;

    public IgnoreRules(bool useDefaults, IEnumerable<string> files, IEnumerable<string> patterns)
    {
        _useDefaults = useDefaults;
        _files = new HashSet<string>(files.Select(NormalizePath), StringComparer.OrdinalIgnoreCase);
        _patterns = patterns
            .Select(p => new Regex(p, RegexOptions.IgnoreCase | RegexOptions.CultureInvariant, PatternTimeout))
            .ToList();
    }

    /// <summary>Why <paramref name="relativePath"/> is ignored, or null when it is not.</summary>
    public string? Reason(string relativePath, Action<string>? warn = null)
    {
        if (_useDefaults && BuiltIn.IsMatch(relativePath)) return "built-in";
        if (_files.Contains(relativePath)) return "Ignore:Files";
        foreach (var pattern in _patterns)
        {
            try
            {
                if (pattern.IsMatch(relativePath)) return $"Ignore:Patterns '{pattern}'";
            }
            catch (RegexMatchTimeoutException)
            {
                warn?.Invoke($"Ignore pattern '{pattern}' timed out on '{relativePath}'; the file is not ignored by it.");
            }
        }
        return null;
    }

    private static string NormalizePath(string path)
    {
        var normalized = path.Replace('\\', '/').TrimStart('/');
        while (normalized.StartsWith("./", StringComparison.Ordinal)) normalized = normalized[2..];
        return normalized;
    }
}

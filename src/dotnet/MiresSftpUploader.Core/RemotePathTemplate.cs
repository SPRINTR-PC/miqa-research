using System.Globalization;
using System.Text.RegularExpressions;

namespace MiresSftpUploader.Core;

/// <summary>
/// The placeholders of the Remote Root and a Source's Remote Path, replaced with the start of the Run (UTC), like the Archive name's
/// <c>{date}</c>: <c>{date}</c> yyyyMMdd, <c>{time}</c> HHmmss, <c>{year}</c>, <c>{month}</c> and <c>{day}</c> (zero-padded).
/// A path without placeholders is used as it is.
/// </summary>
public static partial class RemotePathTemplate
{
    public static IReadOnlyList<string> Placeholders { get; } = ["{date}", "{time}", "{year}", "{month}", "{day}"];

    public static string Expand(string template, DateTimeOffset at)
    {
        if (template.IndexOf('{', StringComparison.Ordinal) < 0) return template;
        var utc = at.UtcDateTime;
        return template
            .Replace("{date}", utc.ToString("yyyyMMdd", CultureInfo.InvariantCulture), StringComparison.Ordinal)
            .Replace("{time}", utc.ToString("HHmmss", CultureInfo.InvariantCulture), StringComparison.Ordinal)
            .Replace("{year}", utc.ToString("yyyy", CultureInfo.InvariantCulture), StringComparison.Ordinal)
            .Replace("{month}", utc.ToString("MM", CultureInfo.InvariantCulture), StringComparison.Ordinal)
            .Replace("{day}", utc.ToString("dd", CultureInfo.InvariantCulture), StringComparison.Ordinal);
    }

    /// <summary>The placeholders in the template that are not known, and any lone brace.</summary>
    public static IReadOnlyList<string> Unknown(string template)
    {
        var unknown = Token().Matches(template).Select(m => m.Value).Where(t => !Placeholders.Contains(t)).ToList();
        var rest = Token().Replace(template, "");
        if (rest.Contains('{') || rest.Contains('}')) unknown.Add("a lone { or }");
        return unknown;
    }

    [GeneratedRegex(@"\{[^{}]*\}")]
    private static partial Regex Token();
}

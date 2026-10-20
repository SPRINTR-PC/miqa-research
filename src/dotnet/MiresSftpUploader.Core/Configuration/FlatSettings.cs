using System.Globalization;
using System.Text.Json;

namespace MiresSftpUploader.Core;

/// <summary>
/// One configuration layer as flat <c>Section:Key</c> to string pairs. An array element is a numeric segment
/// (<c>Sources:0:Name</c>). <see cref="EmptyArrays"/> holds arrays the layer defines as empty, so a higher layer can clear a list.
/// </summary>
internal sealed class FlatSettings
{
    public Dictionary<string, string> Values { get; } = new(StringComparer.OrdinalIgnoreCase);
    public HashSet<string> EmptyArrays { get; } = new(StringComparer.OrdinalIgnoreCase);

    /// <summary>The array roots this layer defines: the key path before its first numeric segment, plus empty arrays.</summary>
    public IEnumerable<string> ArrayRoots()
    {
        var roots = new HashSet<string>(EmptyArrays, StringComparer.OrdinalIgnoreCase);
        foreach (var key in Values.Keys)
        {
            var root = ArrayRootOf(key);
            if (root is not null) roots.Add(root);
        }
        return roots;
    }

    public static string? ArrayRootOf(string key)
    {
        var segments = key.Split(':');
        for (var i = 1; i < segments.Length; i++)
            if (segments[i].Length > 0 && segments[i].All(char.IsAsciiDigit))
                return string.Join(':', segments[..i]);
        return null;
    }

    public static FlatSettings FromJson(string json)
    {
        var flat = new FlatSettings();
        using var doc = JsonDocument.Parse(json, new JsonDocumentOptions { CommentHandling = JsonCommentHandling.Skip, AllowTrailingCommas = true });
        if (doc.RootElement.ValueKind != JsonValueKind.Object)
            throw new JsonException("The top level must be a JSON object.");
        flat.Walk(doc.RootElement, "");
        return flat;
    }

    private void Walk(JsonElement element, string prefix)
    {
        switch (element.ValueKind)
        {
            case JsonValueKind.Object:
                foreach (var p in element.EnumerateObject())
                    Walk(p.Value, prefix.Length == 0 ? p.Name : prefix + ":" + p.Name);
                break;
            case JsonValueKind.Array:
                var i = 0;
                foreach (var item in element.EnumerateArray())
                    Walk(item, prefix + ":" + (i++).ToString(CultureInfo.InvariantCulture));
                if (i == 0) EmptyArrays.Add(prefix);
                break;
            case JsonValueKind.String:
                Values[prefix] = element.GetString()!;
                break;
            case JsonValueKind.True:
                Values[prefix] = "true";
                break;
            case JsonValueKind.False:
                Values[prefix] = "false";
                break;
            case JsonValueKind.Number:
                Values[prefix] = element.GetRawText();
                break;
        }
    }
}

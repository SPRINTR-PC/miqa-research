using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;

namespace MiresSftpUploader.Core;

/// <summary>Turns flat <c>Section:Key</c> settings back into the nested JSON of <c>appsettings.user.json</c>.</summary>
internal static partial class UserFile
{
    public static string ToJson(FlatSettings settings, int configVersion)
    {
        var root = new JsonObject { ["ConfigVersion"] = configVersion };
        var keys = settings.Values.Keys.Concat(settings.EmptyArrays).ToList();
        foreach (var (name, node) in Build("", keys, settings))
            root[name] = node;
        return root.ToJsonString(new JsonSerializerOptions { WriteIndented = true }) + Environment.NewLine;
    }

    private static IEnumerable<(string Name, JsonNode Node)> Build(string prefix, List<string> keys, FlatSettings settings)
    {
        var groups = keys
            .Select(k => (Key: k, Tail: prefix.Length == 0 ? k : k[(prefix.Length + 1)..]))
            .GroupBy(x => x.Tail.Split(':')[0], StringComparer.OrdinalIgnoreCase);

        foreach (var g in groups)
        {
            var path = prefix.Length == 0 ? g.Key : prefix + ":" + g.Key;
            var children = g.Where(x => x.Key.Length > path.Length).Select(x => x.Key).ToList();
            if (settings.EmptyArrays.Contains(path) && children.Count == 0)
                yield return (g.Key, new JsonArray());
            else if (children.Count == 0)
                yield return (g.Key, Scalar(settings.Values[path]));
            else
            {
                var parts = Build(path, children, settings).ToList();
                if (parts.All(p => p.Name.All(char.IsAsciiDigit)))
                {
                    var array = new JsonArray();
                    foreach (var p in parts.OrderBy(p => int.Parse(p.Name))) array.Add(p.Node);
                    yield return (g.Key, array);
                }
                else
                {
                    var obj = new JsonObject();
                    foreach (var p in parts) obj[p.Name] = p.Node;
                    yield return (g.Key, obj);
                }
            }
        }
    }

    private static JsonNode Scalar(string value)
    {
        if (value is "true" or "false") return JsonValue.Create(value == "true");
        if (JsonNumber().IsMatch(value) && JsonNode.Parse(value) is JsonNode number) return number;
        return JsonValue.Create(value);
    }

    [GeneratedRegex(@"^-?(0|[1-9]\d*)(\.\d+)?$")]
    private static partial Regex JsonNumber();
}

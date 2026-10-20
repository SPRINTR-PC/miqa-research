using System.Text.Json;

namespace MiresSftpUploader.Test.Support;

/// <summary>Reads a Manifest JSON document the way a consumer would.</summary>
public static class ManifestTree
{
    /// <summary>Every Archive node of the tree, keyed by its full path inside the Source.</summary>
    public static Dictionary<string, JsonElement> Archives(JsonElement manifest)
    {
        var result = new Dictionary<string, JsonElement>(StringComparer.Ordinal);
        Walk(manifest.GetProperty("root"), "", result);
        return result;
    }

    /// <summary>The flat <c>members</c> of type <paramref name="type"/> (file or archive): path to sha256.</summary>
    public static Dictionary<string, string> Members(JsonElement manifest, string type = "file") =>
        manifest.GetProperty("members").EnumerateArray()
            .Where(m => m.GetProperty("type").GetString() == type)
            .ToDictionary(m => m.GetProperty("path").GetString()!, m => m.GetProperty("sha256").GetString()!, StringComparer.Ordinal);

    private static void Walk(JsonElement directory, string prefix, Dictionary<string, JsonElement> archives)
    {
        foreach (var child in directory.GetProperty("children").EnumerateArray())
        {
            var path = prefix + child.GetProperty("name").GetString();
            switch (child.GetProperty("type").GetString())
            {
                case "directory": Walk(child, path + "/", archives); break;
                case "archive": archives[path] = child; break;
            }
        }
    }
}

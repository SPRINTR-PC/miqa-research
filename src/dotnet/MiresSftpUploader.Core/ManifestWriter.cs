using System.Text.Json;

namespace MiresSftpUploader.Core;

/// <summary>
/// An object physically present on the server that the Manifest lists: a plain file or, for Archives, the zip.
/// Extend with new subtypes (the writer pattern-matches) rather than changing the existing ones.
/// </summary>
internal abstract record ManifestNode(string Path, long Size, string Sha256)
{
    /// <summary>The file left its Source after it was delivered; the server copy is still the one described.</summary>
    public bool MissingAtSource { get; init; }
    /// <summary>The object was written straight to its final name (<c>UploadStrategy</c> Direct), not through a .part and a rename.</summary>
    public bool DirectUpload { get; init; }
}

internal sealed record ManifestFile(string Path, long Size, string Sha256) : ManifestNode(Path, Size, Sha256);

/// <summary>An original file packed into an Archive, with its own hash.</summary>
internal sealed record ManifestArchiveMember(string Path, long Size, string Sha256, DateTimeOffset? Modified);

/// <summary>An Archive and the original files it holds.</summary>
internal sealed record ManifestArchive(string Path, long Size, string Sha256, IReadOnlyList<ManifestArchiveMember> Members)
    : ManifestNode(Path, Size, Sha256);

/// <summary>A file of the Source that has never been delivered (or whose newest version was not).</summary>
internal sealed record ManifestFailure(string Path, string Reason);

/// <summary>Provenance and verdict of the Manifest of one Source.</summary>
internal sealed record ManifestHeader(
    string Source,
    bool Complete,
    Guid RunId,
    DateTimeOffset StartedAt,
    DateTimeOffset CompletedAt,
    string Mode,
    string ToolVersion,
    string MachineName)
{
    /// <summary>Names of Manifests this one replaces (run-stamped Manifests on write-only servers).</summary>
    public IReadOnlyList<string> Supersedes { get; init; } = [];
}

/// <summary>
/// Writes the Manifest JSON (schemaVersion 1) of one Source as a stream. The nodes come from a factory because they are
/// read twice, once for the tree and once for the flat <c>members</c>; they must be sorted by ordinal path.
/// </summary>
internal static class ManifestWriter
{
    public const int SchemaVersion = 1;

    public static void Write(
        Stream output,
        ManifestHeader header,
        IReadOnlyList<ManifestFailure> failures,
        IReadOnlyList<ManifestFailure> deferred,
        Func<IEnumerable<ManifestNode>> nodes)
    {
        using var json = new Utf8JsonWriter(output, new JsonWriterOptions { Indented = true });
        json.WriteStartObject();
        json.WriteNumber("schemaVersion", SchemaVersion);
        json.WriteString("hashAlgorithm", "sha256");
        json.WriteString("generatedAt", header.CompletedAt.UtcDateTime);
        json.WriteBoolean("complete", header.Complete);
        json.WriteString("source", header.Source);

        json.WriteStartObject("run");
        json.WriteString("runId", header.RunId);
        json.WriteString("startedAt", header.StartedAt.UtcDateTime);
        json.WriteString("completedAt", header.CompletedAt.UtcDateTime);
        json.WriteString("mode", header.Mode);
        json.WriteString("toolVersion", header.ToolVersion);
        json.WriteString("machineName", header.MachineName);
        if (header.Supersedes.Count > 0)
        {
            json.WriteStartArray("supersedes");
            foreach (var name in header.Supersedes) json.WriteStringValue(name);
            json.WriteEndArray();
        }
        json.WriteEndObject();

        WriteProblems(json, "failures", failures);
        WriteProblems(json, "deferred", deferred);

        WriteTree(json, nodes());
        WriteMembers(json, nodes());
        json.WriteEndObject();
    }

    /// <summary>
    /// The Flat Manifest in <c>sha256sum -c</c> format: <c>hash␣␣path</c> per object physically on the server, UTF-8, LF,
    /// forward slashes. Like GNU sha256sum, a path holding a backslash or newline gets a leading backslash on the line
    /// and the characters written as <c>\\</c> and <c>\n</c>. The line for the JSON Manifest itself comes last.
    /// </summary>
    public static void WriteFlat(Stream output, IEnumerable<ManifestNode> nodes, string manifestName, string manifestSha256)
    {
        using var writer = new StreamWriter(output, new System.Text.UTF8Encoding(false), 81920, leaveOpen: true) { NewLine = "\n" };
        foreach (var node in nodes) writer.Write(FlatLine(node.Sha256, node.Path));
        writer.Write(FlatLine(manifestSha256, manifestName));
    }

    private static string FlatLine(string sha256, string path)
    {
        var escaped = path.Contains('\\') || path.Contains('\n');
        return (escaped ? "\\" : "") + sha256 + "  " + (escaped ? path.Replace("\\", "\\\\").Replace("\n", "\\n") : path) + "\n";
    }

    private static void WriteProblems(Utf8JsonWriter json, string name, IReadOnlyList<ManifestFailure> problems)
    {
        json.WriteStartArray(name);
        foreach (var problem in problems)
        {
            json.WriteStartObject();
            json.WriteString("path", problem.Path);
            json.WriteString("reason", problem.Reason);
            json.WriteEndObject();
        }
        json.WriteEndArray();
    }

    private static void WriteTree(Utf8JsonWriter json, IEnumerable<ManifestNode> nodes)
    {
        json.WriteStartObject("root");
        json.WriteString("type", "directory");
        json.WriteString("name", "");
        json.WriteStartArray("children");

        var open = new List<string>();
        var written = 0;
        foreach (var node in nodes)
        {
            var parts = node.Path.Split('/');
            var directories = parts.AsSpan(0, parts.Length - 1);

            var common = 0;
            while (common < open.Count && common < directories.Length && open[common] == directories[common]) common++;
            for (var i = open.Count; i > common; i--) CloseDirectory(json);
            open.RemoveRange(common, open.Count - common);
            for (var i = common; i < directories.Length; i++)
            {
                json.WriteStartObject();
                json.WriteString("type", "directory");
                json.WriteString("name", directories[i]);
                json.WriteStartArray("children");
                open.Add(directories[i]);
            }

            WriteTreeNode(json, node, parts[^1]);
            if (++written % 1000 == 0) json.Flush();
        }
        foreach (var _ in open) CloseDirectory(json);

        json.WriteEndArray();
        json.WriteEndObject();
    }

    private static void CloseDirectory(Utf8JsonWriter json)
    {
        json.WriteEndArray();
        json.WriteEndObject();
    }

    private static void WriteTreeNode(Utf8JsonWriter json, ManifestNode node, string name)
    {
        json.WriteStartObject();
        json.WriteString("type", node is ManifestArchive ? "archive" : "file");
        json.WriteString("name", name);
        json.WriteNumber("size", node.Size);
        json.WriteString("sha256", node.Sha256);
        if (node.MissingAtSource) json.WriteBoolean("missingAtSource", true);
        if (node.DirectUpload) json.WriteBoolean("directUpload", true);
        if (node is ManifestArchive archive)
        {
            json.WriteStartArray("members");
            foreach (var member in archive.Members)
            {
                json.WriteStartObject();
                json.WriteString("path", member.Path);
                json.WriteNumber("size", member.Size);
                json.WriteString("sha256", member.Sha256);
                if (member.Modified is { } modified) json.WriteString("modified", modified.UtcDateTime);
                json.WriteEndObject();
            }
            json.WriteEndArray();
        }
        json.WriteEndObject();
    }

    private static void WriteMembers(Utf8JsonWriter json, IEnumerable<ManifestNode> nodes)
    {
        json.WriteStartArray("members");
        var written = 0;
        foreach (var node in nodes)
        {
            json.WriteStartObject();
            json.WriteString("path", node.Path);
            json.WriteString("type", node is ManifestArchive ? "archive" : "file");
            json.WriteNumber("size", node.Size);
            json.WriteString("sha256", node.Sha256);
            if (node.MissingAtSource) json.WriteBoolean("missingAtSource", true);
            if (node.DirectUpload) json.WriteBoolean("directUpload", true);
            json.WriteEndObject();
            if (++written % 1000 == 0) json.Flush();
        }
        json.WriteEndArray();
    }
}

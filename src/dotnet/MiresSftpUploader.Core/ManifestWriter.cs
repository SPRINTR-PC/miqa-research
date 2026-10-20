using System.Text;
using System.Text.Json;

namespace MiresSftpUploader.Core;

/// <summary>Builds the Manifest JSON for one Source (schemaVersion 1, minimal first cut: flat file list and failures).</summary>
internal static class ManifestWriter
{
    public static byte[] Write(
        string source,
        Engine.RunState run,
        DateTimeOffset startedAt,
        DateTimeOffset completedAt,
        IReadOnlyList<Engine.FileEntry> entries,
        IReadOnlyList<Engine.ArchiveEntry>? archives = null)
    {
        using var stream = new MemoryStream();
        using (var json = new Utf8JsonWriter(stream, new JsonWriterOptions { Indented = true }))
        {
            var failures = entries.Where(e => e.Outcome == FileOutcome.Failed).ToList();
            json.WriteStartObject();
            json.WriteNumber("schemaVersion", 1);
            json.WriteString("source", source);
            json.WriteString("runId", run.RunId);
            json.WriteString("startedAt", startedAt);
            json.WriteString("completedAt", completedAt);
            json.WriteBoolean("complete", failures.Count == 0);

            json.WriteStartArray("files");
            foreach (var e in entries.Where(e => e.ArchivePath is null && e.Sha256 is not null && e.Outcome is FileOutcome.Succeeded or FileOutcome.Skipped))
            {
                json.WriteStartObject();
                json.WriteString("path", e.Path);
                json.WriteNumber("size", e.Size);
                json.WriteString("sha256", e.Sha256);
                json.WriteEndObject();
            }
            json.WriteEndArray();

            // An Archive is a file on the server; its members are the original files with their own hashes.
            var byPath = entries.ToDictionary(e => e.Path, StringComparer.Ordinal);
            json.WriteStartArray("archives");
            foreach (var a in archives ?? [])
            {
                json.WriteStartObject();
                json.WriteString("path", a.Path);
                json.WriteString("rule", a.Rule);
                json.WriteNumber("size", a.Size);
                json.WriteString("sha256", a.Sha256);
                json.WriteStartArray("members");
                foreach (var m in a.Members.Select(p => byPath[p]).OrderBy(m => m.EntryName, StringComparer.Ordinal))
                {
                    json.WriteStartObject();
                    json.WriteString("path", m.Path);
                    json.WriteString("entry", m.EntryName);
                    json.WriteNumber("size", m.Size);
                    json.WriteString("sha256", m.Sha256);
                    json.WriteString("modified", m.Modified.UtcDateTime);
                    json.WriteEndObject();
                }
                json.WriteEndArray();
                json.WriteEndObject();
            }
            json.WriteEndArray();

            json.WriteStartArray("failures");
            foreach (var e in failures)
            {
                json.WriteStartObject();
                json.WriteString("path", e.Path);
                json.WriteString("reason", e.Reason);
                json.WriteEndObject();
            }
            json.WriteEndArray();
            json.WriteEndObject();
        }
        return stream.ToArray();
    }
}

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
        IReadOnlyList<Engine.FileEntry> entries)
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
            foreach (var e in entries.Where(e => e.Sha256 is not null && e.Outcome is FileOutcome.Succeeded or FileOutcome.Skipped))
            {
                json.WriteStartObject();
                json.WriteString("path", e.Path);
                json.WriteNumber("size", e.Size);
                json.WriteString("sha256", e.Sha256);
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

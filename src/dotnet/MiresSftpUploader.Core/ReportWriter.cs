using System.Globalization;
using System.Text;
using System.Text.Json;

namespace MiresSftpUploader.Core;

public enum ReportFormat { Json, Csv }

/// <summary>Renders a Report: the summary of one Run plus the outcome of every file, as JSON or CSV.</summary>
internal static class ReportWriter
{
    public static string Extension(ReportFormat format) => format == ReportFormat.Csv ? "csv" : "json";

    public static string Render(RunDetail run, ReportFormat format) =>
        format == ReportFormat.Csv ? Csv(run) : Json(run);

    private static string Json(RunDetail run)
    {
        var summary = run.Summary;
        using var stream = new MemoryStream();
        using (var json = new Utf8JsonWriter(stream, new JsonWriterOptions { Indented = true }))
        {
            json.WriteStartObject();
            json.WriteStartObject("run");
            json.WriteString("runId", summary.RunId);
            json.WriteString("status", summary.Status);
            if (summary.ExitCode is { } exit) json.WriteNumber("exitCode", exit); else json.WriteNull("exitCode");
            json.WriteString("startedBy", summary.StartedBy);
            json.WriteString("mode", summary.Mode);
            json.WriteString("trigger", summary.Trigger);
            json.WriteString("startedAt", summary.StartedAt);
            if (summary.EndedAt is { } ended) json.WriteString("endedAt", ended); else json.WriteNull("endedAt");
            json.WriteStartObject("counts");
            foreach (var (outcome, count) in summary.Counts.OrderBy(kv => kv.Key, StringComparer.Ordinal))
                json.WriteNumber(outcome, count);
            json.WriteEndObject();
            json.WriteEndObject();

            json.WriteStartArray("files");
            foreach (var file in run.Files)
            {
                json.WriteStartObject();
                json.WriteString("source", file.Source);
                json.WriteString("path", file.RelativePath);
                json.WriteString("outcome", file.Outcome);
                json.WriteNumber("bytes", file.Bytes);
                json.WriteNumber("durationMs", file.DurationMs);
                if (file.Reason is null) json.WriteNull("reason"); else json.WriteString("reason", file.Reason);
                json.WriteEndObject();
            }
            json.WriteEndArray();
            json.WriteEndObject();
        }
        return Encoding.UTF8.GetString(stream.ToArray());
    }

    /// <summary>One row per file; the Run columns repeat on every row so each row stands alone. CRLF line ends, RFC 4180 quoting.</summary>
    private static string Csv(RunDetail run)
    {
        var summary = run.Summary;
        var text = new StringBuilder("RunId,StartedAt,Status,ExitCode,StartedBy,Source,Path,Outcome,Bytes,DurationMs,Reason\r\n");
        foreach (var file in run.Files)
        {
            text.AppendJoin(',',
                summary.RunId.ToString(),
                summary.StartedAt.ToString("O", CultureInfo.InvariantCulture),
                summary.Status,
                summary.ExitCode?.ToString(CultureInfo.InvariantCulture) ?? "",
                Quote(summary.StartedBy),
                Quote(file.Source),
                Quote(file.RelativePath),
                file.Outcome,
                file.Bytes.ToString(CultureInfo.InvariantCulture),
                file.DurationMs.ToString(CultureInfo.InvariantCulture),
                Quote(file.Reason ?? ""));
            text.Append("\r\n");
        }
        return text.ToString();
    }

    private static string Quote(string value) =>
        value.AsSpan().IndexOfAny(",\"\r\n") >= 0 ? "\"" + value.Replace("\"", "\"\"") + "\"" : value;
}

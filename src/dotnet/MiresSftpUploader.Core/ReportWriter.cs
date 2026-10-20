using System.Globalization;
using System.Text;
using System.Text.Json;

namespace MiresSftpUploader.Core;

/// <summary>Renders a Report: the summary of one Run plus the outcome of every file, as JSON or CSV.</summary>
internal static class ReportWriter
{
    public static string Extension(ReportFormat format) => format == ReportFormat.Csv ? "csv" : "json";

    /// <summary>Expands the file name pattern; characters that are not valid in a file name become underscores.</summary>
    public static string FileName(string pattern, Guid runId, DateTimeOffset startedAt, ReportFormat format)
    {
        var name = pattern
            .Replace("{runId}", runId.ToString(), StringComparison.Ordinal)
            .Replace("{date}", startedAt.UtcDateTime.ToString("yyyyMMdd", CultureInfo.InvariantCulture), StringComparison.Ordinal)
            .Replace("{time}", startedAt.UtcDateTime.ToString("HHmmss", CultureInfo.InvariantCulture), StringComparison.Ordinal)
            .Replace("{format}", Extension(format), StringComparison.Ordinal)
            .Replace("{ext}", Extension(format), StringComparison.Ordinal);
        return string.Concat(name.Select(c => Array.IndexOf(Path.GetInvalidFileNameChars(), c) >= 0 ? '_' : c));
    }

    /// <summary>
    /// Writes the Report, creating its directory. On Unix the group the Data Directory is shared with gets read and write
    /// (directory 2770 setgid is set by <c>--init-data-dir</c>; files here are 0660); on Windows the inherited ACL applies.
    /// </summary>
    public static void WriteFile(string path, string content)
    {
        var directory = Path.GetDirectoryName(Path.GetFullPath(path));
        if (!string.IsNullOrEmpty(directory) && !Directory.Exists(directory))
        {
            if (OperatingSystem.IsWindows()) Directory.CreateDirectory(directory);
            else Directory.CreateDirectory(directory, UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute
                | UnixFileMode.GroupRead | UnixFileMode.GroupWrite | UnixFileMode.GroupExecute);
        }
        File.WriteAllText(path, content, new UTF8Encoding(false));
        // Set explicitly: the creation mode is reduced by the process umask.
        if (!OperatingSystem.IsWindows())
            File.SetUnixFileMode(path, UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.GroupRead | UnixFileMode.GroupWrite);
    }

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

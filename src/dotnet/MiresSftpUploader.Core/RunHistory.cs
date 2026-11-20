using System.Runtime.CompilerServices;
using System.Text.Json;
using Microsoft.Data.Sqlite;

namespace MiresSftpUploader.Core;

public enum RunFilterKind
{
    All,
    /// <summary>Runs that ended with a non-zero exit code, and Abandoned Runs.</summary>
    NeedsAttention,
    /// <summary>Runs that are still going.</summary>
    Live,
}

public sealed record RunFilter
{
    public RunFilterKind Kind { get; init; } = RunFilterKind.All;
    public int? Limit { get; init; }
}

/// <summary>One Run in the Run History. <see cref="Status"/> is Running, Finished or Abandoned; <see cref="Counts"/> is keyed by File Outcome name.</summary>
public sealed record RunSummary(
    Guid RunId,
    string Status,
    int? ExitCode,
    string StartedBy,
    string Mode,
    string Trigger,
    DateTimeOffset StartedAt,
    DateTimeOffset? EndedAt,
    DateTimeOffset Heartbeat,
    bool CancelRequested,
    IReadOnlyDictionary<string, int> Counts);

/// <summary>The recorded result of one file in one Run.</summary>
public sealed record RunFileOutcome(string Source, string RelativePath, string Outcome, long Bytes, long DurationMs, string? Reason, long? UploadMs = null);

/// <summary><see cref="UploadedBytes"/> is the sum of Bytes over the Succeeded rows of the Run (what it delivered), read beside the counts.</summary>
public sealed record RunDetail(RunSummary Summary, IReadOnlyList<RunFileOutcome> Files, long UploadedBytes = 0);

/// <summary>What the History page needs from the Run History; <see cref="RunHistory"/> is the implementation, view-model tests use a fake.</summary>
public interface IRunHistory
{
    IReadOnlyList<RunSummary> ListRuns(RunFilter? filter = null);
    RunDetail? GetRun(Guid runId);
    string? Export(Guid runId, ReportFormat format);
    /// <summary>Writes the Report of a Run to the configured Report folder; returns its path, or null when there is no such Run.</summary>
    string? SaveReport(Guid runId, ReportFormat format);
    bool RequestCancel(Guid runId);
    int SweepAbandoned();
    IAsyncEnumerable<RunDetail> WatchRun(Guid runId, CancellationToken cancellationToken = default);
}

/// <summary>
/// The Run History of the Upload State: list, inspect, export, cancel and watch Runs, including those started by other
/// OS accounts. Opens short-lived connections, so it never holds up a Run that is writing.
/// </summary>
public sealed class RunHistory(StateSettings state, TimeProvider time, ReportSettings? report = null) : IRunHistory
{
    public IReadOnlyList<RunSummary> ListRuns(RunFilter? filter = null)
    {
        if (!Exists) return [];
        filter ??= new RunFilter();
        using var connection = UploadStateStore.OpenConnection(state.Path!, readOnly: true);
        using var command = connection.CreateCommand();
        var where = filter.Kind switch
        {
            RunFilterKind.NeedsAttention => "WHERE Status = 'Abandoned' OR (ExitCode IS NOT NULL AND ExitCode <> 0)",
            RunFilterKind.Live => "WHERE Status = 'Running'",
            _ => "",
        };
        command.CommandText = $"{SummarySelect} FROM Runs {where} ORDER BY StartedAt DESC, rowid DESC LIMIT $limit";
        command.Parameters.AddWithValue("$limit", filter.Limit ?? -1);
        return ReadSummaries(connection, command);
    }

    public RunDetail? GetRun(Guid runId)
    {
        if (!Exists) return null;
        using var connection = UploadStateStore.OpenConnection(state.Path!, readOnly: true);
        return ReadDetail(connection, runId);
    }

    /// <summary>The Report of a Run (summary plus per-file outcomes) as text, or null when there is no such Run.</summary>
    public string? Export(Guid runId, ReportFormat format) =>
        GetRun(runId) is { } detail ? ReportWriter.Render(detail, format) : null;

    public string? SaveReport(Guid runId, ReportFormat format)
    {
        if (GetRun(runId) is not { } detail) return null;
        var settings = report ?? new ReportSettings();
        var directory = settings.Directory
            ?? Path.Combine(Path.GetDirectoryName(Path.GetFullPath(state.Path!))!, "reports");
        var path = Path.Combine(directory, ReportWriter.FileName(settings.FileNamePattern, runId, detail.Summary.StartedAt, format));
        ReportWriter.WriteFile(path, ReportWriter.Render(detail, format));
        return path;
    }

    /// <summary>
    /// Asks a live Run, whoever started it, to stop. The Run's Engine polls the request and ends with exit code 130.
    /// Returns false when there is no such live Run.
    /// </summary>
    public bool RequestCancel(Guid runId)
    {
        if (!Exists) return false;
        using var connection = UploadStateStore.OpenConnection(state.Path!);
        using var command = connection.CreateCommand();
        command.CommandText = "UPDATE Runs SET CancelRequested = 1 WHERE Id = $id AND Status = 'Running'";
        command.Parameters.AddWithValue("$id", runId.ToString());
        return command.ExecuteNonQuery() > 0;
    }

    /// <summary>
    /// Marks Runs whose heartbeat is older than <see cref="StateSettings.AbandonedAfter"/> as Abandoned and their in-flight
    /// files as Failed, so the next Run retries them and cleans up their .part files. Returns how many Runs were marked.
    /// </summary>
    public int SweepAbandoned()
    {
        if (!Exists) return 0;
        using var connection = UploadStateStore.OpenConnection(state.Path!);
        using var transaction = connection.BeginTransaction();
        var abandoned = UploadStateStore.AbandonStale(connection, time.GetUtcNow(), state.AbandonedAfter);
        transaction.Commit();
        return abandoned;
    }

    /// <summary>
    /// Follows a Run, typically another account's live one, by polling the Upload State (about every second).
    /// Yields a snapshot whenever something changed and ends after the snapshot in which the Run is no longer
    /// running. A Run whose heartbeat went stale is swept first, so it ends as Abandoned.
    /// </summary>
    public async IAsyncEnumerable<RunDetail> WatchRun(Guid runId, [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        string? last = null;
        while (true)
        {
            cancellationToken.ThrowIfCancellationRequested();
            SweepAbandoned();
            var detail = GetRun(runId);
            if (detail is null) yield break;

            var fingerprint = $"{detail.Summary.Status}|{detail.Summary.ExitCode}|{detail.Summary.Heartbeat.UtcTicks}|{detail.Summary.CancelRequested}|{detail.Files.Count}";
            if (fingerprint != last)
            {
                last = fingerprint;
                yield return detail;
            }
            if (detail.Summary.Status != "Running") yield break;
            await Task.Delay(state.WatchInterval, time, cancellationToken);
        }
    }

    private bool Exists => state.Path is { Length: > 0 } path && File.Exists(path);

    // ---- SQL ----

    private const string SummarySelect =
        "SELECT Id, Status, ExitCode, StartedBy, Mode, Trigger, StartedAt, EndedAt, Heartbeat, CancelRequested, Counts";

    private static List<RunSummary> ReadSummaries(SqliteConnection connection, SqliteCommand command)
    {
        var rows = new List<(RunSummary Summary, string? CountsJson)>();
        using (var reader = command.ExecuteReader())
            while (reader.Read())
            {
                var summary = new RunSummary(
                    Guid.Parse(reader.GetString(0)), reader.GetString(1),
                    reader.IsDBNull(2) ? null : reader.GetInt32(2),
                    reader.GetString(3), reader.GetString(4), reader.GetString(5),
                    new DateTimeOffset(reader.GetInt64(6), TimeSpan.Zero),
                    reader.IsDBNull(7) ? null : new DateTimeOffset(reader.GetInt64(7), TimeSpan.Zero),
                    new DateTimeOffset(reader.GetInt64(8), TimeSpan.Zero),
                    reader.GetInt64(9) != 0,
                    new Dictionary<string, int>());
                rows.Add((summary, reader.IsDBNull(10) ? null : reader.GetString(10)));
            }

        return rows.Select(r => r.Summary with { Counts = r.CountsJson is null ? CountLive(connection, r.Summary.RunId) : ParseCounts(r.CountsJson) }).ToList();
    }

    /// <summary>A Run that has not finished has no stored counts yet; count what it has recorded so far.</summary>
    private static Dictionary<string, int> CountLive(SqliteConnection connection, Guid runId)
    {
        using var command = connection.CreateCommand();
        command.CommandText = "SELECT Outcome, COUNT(*) FROM RunFiles WHERE RunId = $id GROUP BY Outcome";
        command.Parameters.AddWithValue("$id", runId.ToString());
        var counts = new Dictionary<string, int>();
        using var reader = command.ExecuteReader();
        while (reader.Read()) counts[reader.GetString(0)] = reader.GetInt32(1);
        return counts;
    }

    private static Dictionary<string, int> ParseCounts(string json) =>
        JsonSerializer.Deserialize<Dictionary<string, int>>(json) ?? new Dictionary<string, int>();

    private static RunDetail? ReadDetail(SqliteConnection connection, Guid runId)
    {
        using var command = connection.CreateCommand();
        command.CommandText = $"{SummarySelect} FROM Runs WHERE Id = $id";
        command.Parameters.AddWithValue("$id", runId.ToString());
        var summary = ReadSummaries(connection, command).SingleOrDefault();
        if (summary is null) return null;

        // A database no Run has migrated yet (schema 3) has no UploadMs column.
        using var versionCommand = connection.CreateCommand();
        versionCommand.CommandText = "PRAGMA user_version";
        var hasUploadMs = Convert.ToInt32(versionCommand.ExecuteScalar(), System.Globalization.CultureInfo.InvariantCulture) >= 4;
        using var files = connection.CreateCommand();
        files.CommandText = $"""
            SELECT f.Source, f.RelativePath, r.Outcome, r.Bytes, r.DurationMs, r.Error, {(hasUploadMs ? "r.UploadMs" : "NULL")}
            FROM RunFiles r JOIN Files f ON f.Id = r.FileId
            WHERE r.RunId = $id ORDER BY f.Source, f.RelativePath
            """;
        files.Parameters.AddWithValue("$id", runId.ToString());
        var list = new List<RunFileOutcome>();
        using var reader = files.ExecuteReader();
        while (reader.Read())
            list.Add(new RunFileOutcome(reader.GetString(0), reader.GetString(1), reader.GetString(2),
                reader.GetInt64(3), reader.GetInt64(4), reader.IsDBNull(5) ? null : reader.GetString(5), reader.IsDBNull(6) ? null : reader.GetInt64(6)));
        return new RunDetail(summary, list, list.Where(f => f.Outcome == "Succeeded").Sum(f => f.Bytes));
    }
}

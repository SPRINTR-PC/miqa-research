
namespace MiresSftpUploader.Core;

/// <summary>Latest known state of one uploaded file. <see cref="Status"/> is Succeeded, Failed, Uploading or Missing.</summary>
public sealed record FileRecord(string Source, string RelativePath, string Status, long Size, string? Sha256, string? LastError);

/// <summary>One Run as recorded in the Upload State. <see cref="Status"/> is Running, Finished or Abandoned.</summary>
public sealed record RunRecord(Guid RunId, string Status, int? ExitCode, string StartedBy, DateTimeOffset StartedAt, DateTimeOffset? EndedAt);

/// <summary>
/// Read-only view of the Upload State database, for the History view and for tests.
/// Opens short-lived connections, so it never holds up a Run that is writing.
/// </summary>
public static class UploadState
{
    public static IReadOnlyList<FileRecord> ReadFiles(string databasePath)
    {
        using var connection = UploadStateStore.OpenConnection(databasePath, readOnly: true);
        using var command = connection.CreateCommand();
        command.CommandText = "SELECT Source, RelativePath, Status, Size, Sha256, LastError FROM Files ORDER BY Source, RelativePath";
        using var rows = command.ExecuteReader();
        var result = new List<FileRecord>();
        while (rows.Read())
            result.Add(new FileRecord(rows.GetString(0), rows.GetString(1), rows.GetString(2), rows.GetInt64(3),
                rows.IsDBNull(4) ? null : rows.GetString(4), rows.IsDBNull(5) ? null : rows.GetString(5)));
        return result;
    }

    public static IReadOnlyList<RunRecord> ReadRuns(string databasePath)
    {
        using var connection = UploadStateStore.OpenConnection(databasePath, readOnly: true);
        using var command = connection.CreateCommand();
        command.CommandText = "SELECT Id, Status, ExitCode, StartedBy, StartedAt, EndedAt FROM Runs ORDER BY StartedAt";
        using var rows = command.ExecuteReader();
        var result = new List<RunRecord>();
        while (rows.Read())
            result.Add(new RunRecord(Guid.Parse(rows.GetString(0)), rows.GetString(1),
                rows.IsDBNull(2) ? null : rows.GetInt32(2), rows.GetString(3),
                new DateTimeOffset(rows.GetInt64(4), TimeSpan.Zero),
                rows.IsDBNull(5) ? null : new DateTimeOffset(rows.GetInt64(5), TimeSpan.Zero)));
        return result;
    }
}

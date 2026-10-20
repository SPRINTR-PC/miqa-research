using System.Globalization;
using System.Text.Json;
using System.Threading.Channels;
using Microsoft.Data.Sqlite;

namespace MiresSftpUploader.Core;

/// <summary>The database was written by a newer version of the app; this version must not touch it.</summary>
public sealed class UploadStateTooNewException(int found, int supported)
    : Exception($"Upload State schema version {found} is newer than this app supports ({supported}). Update the app.")
{
    public int Found { get; } = found;
    public int Supported { get; } = supported;
}

/// <summary>Identity of one file in the Upload State: Destination (host:port), Remote Path, Source name, relative path.</summary>
internal readonly record struct FileKey(string Destination, string RemotePath, string Source, string RelativePath);

/// <summary>What the Upload State knows about a file from earlier Runs.</summary>
internal sealed record PriorFile(string Status, long Size, long MtimeTicks, string? Sha256);

/// <summary>An upload that was in flight when its Run died: the server object to remove.</summary>
internal sealed record OrphanPart(string Destination, string PartPath);

/// <summary>
/// The SQLite (WAL) store behind the Upload State. All writes go through one writer task fed by a channel;
/// reads open short-lived connections. Not a seam: tests use a real database file.
/// </summary>
internal sealed class UploadStateStore : IAsyncDisposable
{
    internal const int SchemaVersion = 1;

    private static readonly string[] Migrations =
    [
        // 1: initial schema
        """
        CREATE TABLE Runs (
            Id              TEXT PRIMARY KEY,
            StartedAt       INTEGER NOT NULL,
            EndedAt         INTEGER NULL,
            Mode            TEXT NOT NULL,
            Trigger         TEXT NOT NULL,
            ExitCode        INTEGER NULL,
            Status          TEXT NOT NULL,
            Counts          TEXT NULL,
            StartedBy       TEXT NOT NULL,
            Heartbeat       INTEGER NOT NULL,
            CancelRequested INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE Files (
            Id            INTEGER PRIMARY KEY,
            Destination   TEXT NOT NULL,
            RemotePath    TEXT NOT NULL,
            Source        TEXT NOT NULL,
            RelativePath  TEXT NOT NULL,
            Sha256        TEXT NULL,
            Size          INTEGER NOT NULL,
            Mtime         INTEGER NOT NULL,
            Status        TEXT NOT NULL,
            LastSuccessAt INTEGER NULL,
            LastError     TEXT NULL,
            PartPath      TEXT NULL,
            MissingSince  INTEGER NULL,
            UNIQUE (Destination, RemotePath, Source, RelativePath)
        );
        CREATE INDEX IX_Files_Status ON Files (Status);
        CREATE TABLE RunFiles (
            RunId      TEXT NOT NULL REFERENCES Runs (Id) ON DELETE CASCADE,
            FileId     INTEGER NOT NULL REFERENCES Files (Id) ON DELETE CASCADE,
            Outcome    TEXT NOT NULL,
            Bytes      INTEGER NOT NULL DEFAULT 0,
            DurationMs INTEGER NOT NULL DEFAULT 0,
            Error      TEXT NULL,
            RecordedAt INTEGER NOT NULL,
            PRIMARY KEY (RunId, FileId)
        );
        CREATE INDEX IX_RunFiles_RecordedAt ON RunFiles (RecordedAt);
        CREATE TABLE ArchiveMembers (
            ArchiveFileId INTEGER NOT NULL REFERENCES Files (Id) ON DELETE CASCADE,
            MemberPath    TEXT NOT NULL,
            Size          INTEGER NOT NULL,
            Mtime         INTEGER NOT NULL,
            Sha256        TEXT NOT NULL,
            PRIMARY KEY (ArchiveFileId, MemberPath)
        );
        """,
    ];

    private const int BatchSize = 200;

    private readonly string _path;
    private readonly Channel<WriteOp> _queue = Channel.CreateUnbounded<WriteOp>(new UnboundedChannelOptions { SingleReader = true });
    private readonly Task _writer;
    private readonly SqliteConnection _writeConnection;
    private Exception? _fault;

    private UploadStateStore(string path, SqliteConnection writeConnection)
    {
        _path = path;
        _writeConnection = writeConnection;
        _writer = Task.Run(WriterLoop);
    }

    /// <summary>Opens (creating and migrating when needed) the database at <paramref name="path"/>.</summary>
    /// <exception cref="UploadStateTooNewException">The schema is newer than this app.</exception>
    public static UploadStateStore Open(string path, TimeProvider time)
    {
        var directory = System.IO.Path.GetDirectoryName(System.IO.Path.GetFullPath(path));
        if (!string.IsNullOrEmpty(directory)) Directory.CreateDirectory(directory);

        // SQLite gives -wal and -shm the mode of the database file, so it must be group-writable before SQLite creates it.
        DataDirectory.EnsureGroupWritable(path, createIfMissing: true);
        var connection = OpenConnection(path);
        try
        {
            if (!string.Equals(Scalar(connection, "PRAGMA journal_mode"), "wal", StringComparison.OrdinalIgnoreCase))
                Execute(connection, "PRAGMA journal_mode=WAL");

            var current = Convert.ToInt32(Scalar(connection, "PRAGMA user_version"), CultureInfo.InvariantCulture);
            if (current > SchemaVersion) throw new UploadStateTooNewException(current, SchemaVersion);
            if (current < SchemaVersion)
            {
                if (current > 0) BackupBeforeMigrating(connection, path, time);
                for (var version = current + 1; version <= SchemaVersion; version++)
                {
                    using var tx = connection.BeginTransaction();
                    Execute(connection, Migrations[version - 1], tx);
                    Execute(connection, $"PRAGMA user_version = {version}", tx);
                    tx.Commit();
                }
            }
            return new UploadStateStore(path, connection);
        }
        catch
        {
            connection.Dispose();
            throw;
        }
    }

    /// <summary>Opens a connection with the per-connection pragmas applied.</summary>
    internal static SqliteConnection OpenConnection(string path, bool readOnly = false)
    {
        var connection = new SqliteConnection(new SqliteConnectionStringBuilder
        {
            DataSource = path,
            Mode = readOnly ? SqliteOpenMode.ReadOnly : SqliteOpenMode.ReadWriteCreate,
            Pooling = false,
            DefaultTimeout = 30,
        }.ToString());
        connection.Open();
        Execute(connection, "PRAGMA busy_timeout=30000");
        Execute(connection, "PRAGMA foreign_keys=ON");
        if (!readOnly)
        {
            Execute(connection, "PRAGMA synchronous=NORMAL");
            Execute(connection, "PRAGMA journal_size_limit=67108864");
        }
        return connection;
    }

    private static void BackupBeforeMigrating(SqliteConnection connection, string path, TimeProvider time)
    {
        var stamp = time.GetUtcNow().ToString("yyyyMMddHHmmss", CultureInfo.InvariantCulture);
        var backup = $"{path}.v{Scalar(connection, "PRAGMA user_version")}-{stamp}.bak";
        using var command = connection.CreateCommand();
        command.CommandText = "VACUUM INTO $target";
        command.Parameters.AddWithValue("$target", backup);
        command.ExecuteNonQuery();
        DataDirectory.EnsureGroupWritable(backup);
    }

    // ---- Writes (queued) ----

    public Task BeginRunAsync(Guid runId, DateTimeOffset now, string mode, string trigger, string startedBy) =>
        Enqueue(c => Exec(c, """
            INSERT INTO Runs (Id, StartedAt, Mode, Trigger, Status, StartedBy, Heartbeat)
            VALUES ($id, $now, $mode, $trigger, 'Running', $by, $now)
            """, ("$id", runId.ToString()), ("$now", now.UtcTicks), ("$mode", mode), ("$trigger", trigger), ("$by", startedBy)));

    public Task HeartbeatAsync(Guid runId, DateTimeOffset now) =>
        Enqueue(c => Exec(c, "UPDATE Runs SET Heartbeat = $now WHERE Id = $id", ("$id", runId.ToString()), ("$now", now.UtcTicks)));

    public Task FinishRunAsync(Guid runId, DateTimeOffset now, int exitCode, IReadOnlyDictionary<FileOutcome, int> counts) =>
        Enqueue(c => Exec(c, """
            UPDATE Runs SET EndedAt = $now, Heartbeat = $now, ExitCode = $exit, Status = 'Finished', Counts = $counts WHERE Id = $id
            """, ("$id", runId.ToString()), ("$now", now.UtcTicks), ("$exit", exitCode),
            ("$counts", JsonSerializer.Serialize(counts.ToDictionary(kv => kv.Key.ToString(), kv => kv.Value)))));

    /// <summary>Durable before the upload starts: records the in-flight file and the server object that must be cleaned up if the Run dies.</summary>
    public Task MarkUploadingAsync(FileKey key, long size, long mtimeTicks, string partPath) =>
        Enqueue(c => Upsert(c, key, "Uploading", size, mtimeTicks, sha256: null, error: null, partPath, success: null));

    public void RecordSucceeded(Guid runId, FileKey key, long size, long mtimeTicks, string sha256, DateTimeOffset now, TimeSpan duration) =>
        _ = Enqueue(c =>
        {
            Upsert(c, key, "Succeeded", size, mtimeTicks, sha256, error: null, partPath: null, success: now.UtcTicks);
            InsertRunFile(c, runId, key, "Succeeded", size, duration, null, now);
        });

    public void RecordSkipped(Guid runId, FileKey key, DateTimeOffset now, string reason = "unchanged") =>
        _ = Enqueue(c => InsertRunFile(c, runId, key, "Skipped", 0, TimeSpan.Zero, reason, now));

    /// <summary>The file is no longer in its Source. The server copy is left alone.</summary>
    public Task MarkMissingFileAsync(FileKey key, DateTimeOffset now) =>
        Enqueue(c => Exec(c, """
            UPDATE Files SET Status='Missing', MissingSince=$now, PartPath=NULL
            WHERE Destination=$d AND RemotePath=$r AND Source=$s AND RelativePath=$p
            """, ("$now", now.UtcTicks), ("$d", key.Destination), ("$r", key.RemotePath), ("$s", key.Source), ("$p", key.RelativePath)));

    public void RecordFailed(Guid runId, FileKey key, long size, long mtimeTicks, string error, DateTimeOffset now, TimeSpan duration) =>
        _ = Enqueue(c =>
        {
            Upsert(c, key, "Failed", size, mtimeTicks, sha256: null, error, partPath: null, success: null);
            InsertRunFile(c, runId, key, "Failed", 0, duration, error, now);
        });

    /// <summary>Marks every recorded file of the Source that is no longer listed as Missing. Remote files are never touched.</summary>
    public Task MarkMissingAsync(string destination, string remotePath, string source, IReadOnlySet<string> stillListed, DateTimeOffset now) =>
        Enqueue(c =>
        {
            var vanished = new List<long>();
            using (var read = c.CreateCommand())
            {
                read.CommandText = "SELECT Id, RelativePath FROM Files WHERE Destination=$d AND RemotePath=$r AND Source=$s AND Status <> 'Missing'";
                read.Parameters.AddWithValue("$d", destination);
                read.Parameters.AddWithValue("$r", remotePath);
                read.Parameters.AddWithValue("$s", source);
                using var rows = read.ExecuteReader();
                while (rows.Read())
                    if (!stillListed.Contains(rows.GetString(1))) vanished.Add(rows.GetInt64(0));
            }
            foreach (var id in vanished)
                Exec(c, "UPDATE Files SET Status='Missing', MissingSince=$now, PartPath=NULL WHERE Id=$id", ("$id", id), ("$now", now.UtcTicks));
        });

    /// <summary>Forgets the Source's files so the next scan uploads everything again.</summary>
    public Task ResetSourceAsync(string destination, string remotePath, string source) =>
        Enqueue(c => Exec(c, "DELETE FROM Files WHERE Destination=$d AND RemotePath=$r AND Source=$s",
            ("$d", destination), ("$r", remotePath), ("$s", source)));

    /// <summary>
    /// Marks Runs with a stale heartbeat as Abandoned and their in-flight files as Failed.
    /// Returns the server objects recorded for those files; only those may be cleaned up.
    /// </summary>
    public async Task<IReadOnlyList<OrphanPart>> SweepAbandonedAsync(DateTimeOffset now, TimeSpan staleAfter, string destination)
    {
        var orphans = new List<OrphanPart>();
        await Enqueue(c =>
        {
            AbandonStale(c, now, staleAfter);
            using var read = c.CreateCommand();
            read.CommandText = "SELECT Destination, PartPath FROM Files WHERE Status='Failed' AND PartPath IS NOT NULL AND Destination=$d";
            read.Parameters.AddWithValue("$d", destination);
            using var rows = read.ExecuteReader();
            while (rows.Read()) orphans.Add(new OrphanPart(rows.GetString(0), rows.GetString(1)));
        });
        return orphans;
    }

    /// <summary>The recorded server objects of these orphans are gone (or were never there); forget them.</summary>
    public Task ForgetOrphansAsync(string destination) =>
        Enqueue(c => Exec(c, "UPDATE Files SET PartPath=NULL WHERE Status='Failed' AND Destination=$d", ("$d", destination)));

    /// <summary>
    /// Marks Runs with a stale heartbeat Abandoned. When no Run is live any more, the files they left Uploading become Failed
    /// but keep their recorded .part path, so the next Run (which holds the connection) can still clean the server up.
    /// Returns how many Runs were marked.
    /// </summary>
    internal static int AbandonStale(SqliteConnection c, DateTimeOffset now, TimeSpan staleAfter)
    {
        var abandoned = Exec(c, """
            UPDATE Runs SET Status='Abandoned', EndedAt=Heartbeat WHERE Status='Running' AND Heartbeat < $stale
            """, ("$stale", now.UtcTicks - staleAfter.Ticks));
        // The single-instance lock allows one live Run, so Uploading files with no live Run belong to Abandoned ones.
        Exec(c, """
            UPDATE Files SET Status='Failed', LastError='Abandoned Run'
            WHERE Status='Uploading' AND NOT EXISTS (SELECT 1 FROM Runs WHERE Status='Running')
            """);
        return abandoned;
    }

    /// <summary>True when another account asked for this Run to stop.</summary>
    public bool IsCancelRequested(Guid runId)
    {
        using var connection = OpenConnection(_path, readOnly: true);
        using var command = connection.CreateCommand();
        command.CommandText = "SELECT CancelRequested FROM Runs WHERE Id = $id";
        command.Parameters.AddWithValue("$id", runId.ToString());
        return Convert.ToInt64(command.ExecuteScalar() ?? 0L, CultureInfo.InvariantCulture) != 0;
    }

    /// <summary>Deletes expired per-Run file outcomes and long-Missing files, in chunks to keep the WAL small.</summary>
    public Task PruneAsync(DateTimeOffset now, TimeSpan runFilesRetention, TimeSpan missingRetention) =>
        Enqueue(c =>
        {
            while (Exec(c, """
                DELETE FROM RunFiles WHERE rowid IN (SELECT rowid FROM RunFiles WHERE RecordedAt < $cut LIMIT 5000)
                """, ("$cut", (now - runFilesRetention).UtcTicks)) > 0) { }
            while (Exec(c, """
                DELETE FROM Files WHERE Id IN (SELECT Id FROM Files WHERE Status='Missing' AND MissingSince < $cut LIMIT 5000)
                """, ("$cut", (now - missingRetention).UtcTicks)) > 0) { }
        });

    // ---- Reads ----

    public bool RunExists(Guid runId)
    {
        using var connection = OpenConnection(_path, readOnly: true);
        using var command = connection.CreateCommand();
        command.CommandText = "SELECT 1 FROM Runs WHERE Id = $id";
        command.Parameters.AddWithValue("$id", runId.ToString());
        return command.ExecuteScalar() is not null;
    }

    /// <summary>Files that failed in the given Run and are still Failed, for a retry.</summary>
    public List<(string RemotePath, string Source, string RelativePath)> LoadFailedOf(Guid runId, string destination)
    {
        using var connection = OpenConnection(_path, readOnly: true);
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT f.RemotePath, f.Source, f.RelativePath FROM RunFiles r JOIN Files f ON f.Id = r.FileId
            WHERE r.RunId = $id AND r.Outcome = 'Failed' AND f.Status = 'Failed' AND f.Destination = $d
            """;
        command.Parameters.AddWithValue("$id", runId.ToString());
        command.Parameters.AddWithValue("$d", destination);
        var result = new List<(string, string, string)>();
        using var rows = command.ExecuteReader();
        while (rows.Read()) result.Add((rows.GetString(0), rows.GetString(1), rows.GetString(2)));
        return result;
    }

    public Dictionary<string, PriorFile> LoadSource(string destination, string remotePath, string source)
    {
        using var connection = OpenConnection(_path, readOnly: true);
        return LoadSource(connection, destination, remotePath, source);
    }

    private static Dictionary<string, PriorFile> LoadSource(SqliteConnection connection, string destination, string remotePath, string source)
    {
        using var command = connection.CreateCommand();
        command.CommandText = """
            SELECT RelativePath, Status, Size, Mtime, Sha256 FROM Files WHERE Destination=$d AND RemotePath=$r AND Source=$s
            """;
        command.Parameters.AddWithValue("$d", destination);
        command.Parameters.AddWithValue("$r", remotePath);
        command.Parameters.AddWithValue("$s", source);
        var result = new Dictionary<string, PriorFile>(StringComparer.Ordinal);
        using var rows = command.ExecuteReader();
        while (rows.Read())
            result[rows.GetString(0)] = new PriorFile(rows.GetString(1), rows.GetInt64(2), rows.GetInt64(3), rows.IsDBNull(4) ? null : rows.GetString(4));
        return result;
    }

    /// <summary>
    /// What a Dry Run knows about a Source: reads the database without opening a store, creating, migrating or
    /// writing anything. A missing, empty or newer database yields no prior files.
    /// </summary>
    public static Dictionary<string, PriorFile> ReadPriorFiles(string path, string destination, string remotePath, string source)
    {
        var none = new Dictionary<string, PriorFile>(StringComparer.Ordinal);
        if (!File.Exists(path)) return none;
        try
        {
            // immutable=1: no locks and no -wal/-shm files are created, so the directory is left exactly as found.
            // Changes still in the write-ahead log of a Run in progress are not seen, which is fine for a preview.
            var uri = new Uri(System.IO.Path.GetFullPath(path)).AbsoluteUri + "?mode=ro&immutable=1";
            using var connection = new SqliteConnection(new SqliteConnectionStringBuilder { DataSource = uri, Pooling = false }.ToString());
            connection.Open();
            if (Convert.ToInt32(Scalar(connection, "PRAGMA user_version"), CultureInfo.InvariantCulture) != SchemaVersion) return none;
            return LoadSource(connection, destination, remotePath, source);
        }
        catch (SqliteException)
        {
            return none;
        }
    }

    // ---- Writer ----

    private sealed record WriteOp(Action<SqliteConnection> Work, TaskCompletionSource Done);

    private Task Enqueue(Action<SqliteConnection> work)
    {
        var done = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        if (!_queue.Writer.TryWrite(new WriteOp(work, done)))
            done.SetException(new ObjectDisposedException(nameof(UploadStateStore)));
        return done.Task;
    }

    /// <summary>Waits until every write queued so far is committed; rethrows the first write failure.</summary>
    public async Task FlushAsync()
    {
        await Enqueue(_ => { });
        if (_fault is not null) throw _fault;
    }

    private async Task WriterLoop()
    {
        var batch = new List<WriteOp>(BatchSize);
        while (await _queue.Reader.WaitToReadAsync())
        {
            batch.Clear();
            while (batch.Count < BatchSize && _queue.Reader.TryRead(out var op)) batch.Add(op);
            try
            {
                using var tx = _writeConnection.BeginTransaction();
                foreach (var op in batch) op.Work(_writeConnection);
                tx.Commit();
                foreach (var op in batch) op.Done.TrySetResult();
            }
            catch (Exception ex)
            {
                _fault ??= ex;
                foreach (var op in batch) op.Done.TrySetException(ex);
            }
        }
    }

    public async ValueTask DisposeAsync()
    {
        _queue.Writer.TryComplete();
        await _writer;
        try { Execute(_writeConnection, "PRAGMA wal_checkpoint(TRUNCATE)"); }
        catch (SqliteException) { /* another process is reading; the next Run checkpoints */ }
        await _writeConnection.DisposeAsync();
    }

    // ---- SQL helpers ----

    private static void Upsert(SqliteConnection c, FileKey key, string status, long size, long mtime, string? sha256, string? error, string? partPath, long? success) =>
        Exec(c, """
            INSERT INTO Files (Destination, RemotePath, Source, RelativePath, Sha256, Size, Mtime, Status, LastSuccessAt, LastError, PartPath)
            VALUES ($d, $r, $s, $p, $sha, $size, $mtime, $status, $success, $error, $part)
            ON CONFLICT (Destination, RemotePath, Source, RelativePath) DO UPDATE SET
                Sha256 = COALESCE($sha, Sha256),
                Size = $size, Mtime = $mtime, Status = $status,
                LastSuccessAt = COALESCE($success, LastSuccessAt),
                LastError = $error, PartPath = $part, MissingSince = NULL
            """,
            ("$d", key.Destination), ("$r", key.RemotePath), ("$s", key.Source), ("$p", key.RelativePath),
            ("$sha", sha256), ("$size", size), ("$mtime", mtime), ("$status", status),
            ("$success", success), ("$error", error), ("$part", partPath));

    private static void InsertRunFile(SqliteConnection c, Guid runId, FileKey key, string outcome, long bytes, TimeSpan duration, string? error, DateTimeOffset now) =>
        Exec(c, """
            INSERT OR REPLACE INTO RunFiles (RunId, FileId, Outcome, Bytes, DurationMs, Error, RecordedAt)
            SELECT $run, Id, $outcome, $bytes, $ms, $error, $now FROM Files
            WHERE Destination=$d AND RemotePath=$r AND Source=$s AND RelativePath=$p
            """,
            ("$run", runId.ToString()), ("$outcome", outcome), ("$bytes", bytes), ("$ms", (long)duration.TotalMilliseconds),
            ("$error", error), ("$now", now.UtcTicks),
            ("$d", key.Destination), ("$r", key.RemotePath), ("$s", key.Source), ("$p", key.RelativePath));

    internal static int Exec(SqliteConnection c, string sql, params (string Name, object? Value)[] parameters)
    {
        using var command = c.CreateCommand();
        command.CommandText = sql;
        foreach (var (name, value) in parameters) command.Parameters.AddWithValue(name, value ?? DBNull.Value);
        return command.ExecuteNonQuery();
    }

    private static void Execute(SqliteConnection c, string sql, SqliteTransaction? tx = null)
    {
        using var command = c.CreateCommand();
        command.Transaction = tx;
        command.CommandText = sql;
        command.ExecuteNonQuery();
    }

    private static string Scalar(SqliteConnection c, string sql)
    {
        using var command = c.CreateCommand();
        command.CommandText = sql;
        return Convert.ToString(command.ExecuteScalar(), CultureInfo.InvariantCulture) ?? "";
    }
}

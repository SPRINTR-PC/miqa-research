using Microsoft.Extensions.Logging;

namespace MiresSftpUploader.Core;

// Post-upload Move: once every outcome of the Run is committed to the Upload State, files whose outcome is final leave
// their Source: to one location after success, to another after failure.
public sealed partial class Engine
{
    /// <summary>
    /// Moves, per Source, the files with a final outcome. Success: Succeeded, or Skipped because unchanged (an Archive's
    /// members are Succeeded or Skipped together once the Archive is committed). Failure: Failed, except
    /// ChangedDuringUpload and ChangedDuringArchive, whose files are still being written to. Ignored, Too Recent and Missing
    /// files never move. A move that does not happen is a warning; the upload outcome stays what it was.
    /// </summary>
    private async Task MoveFilesAsync(IReadOnlyList<ISource> sources, RunState run, CancellationToken ct)
    {
        var configured = sources
            .Select(source => (Source: source, Config: _settings.SourceConfigs.FirstOrDefault(c => string.Equals(c.Name, source.Name, StringComparison.OrdinalIgnoreCase))?.AfterUpload))
            .Where(s => s.Config is { } c && (c.OnSuccess.Action == MoveAction.Move || c.OnFailure.Action == MoveAction.Move))
            .ToList();
        if (configured.Count == 0) return;

        // The outcomes must be durable before the first file leaves its Source.
        if (run.Store is { } store) await store.FlushAsync();

        foreach (var (source, config) in configured)
        {
            var remotePath = RemotePathOf(source);
            var entries = run.OwnEntries(source.Name);
            foreach (var entry in entries)
            {
                ct.ThrowIfCancellationRequested();
                var target = TargetFor(entry, config!);
                if (target is null) continue;

                var result = await MoveOneAsync(source, entry, target, ct);
                if (result is null) continue;
                if (result.Status == MoveStatus.Moved)
                {
                    run.MarkMoved(source.Name, entry.Path);
                    run.Report(new FileMoved(source.Name, entry.Path));
                    _logger.LogInformation("{Source}/{Path}: moved away", source.Name, entry.Path);
                    if (run.Store is { } moved && entry.ArchivePath is null)
                        await moved.RecordMovedAwayAsync(new FileKey(_settings.Destination, remotePath, source.Name, entry.Path));
                }
                else
                {
                    run.CountMoveFailure();
                    run.Warn($"{source.Name}/{entry.Path}: not moved ({result.Detail}); the file stays in the Source");
                }
            }

            // An Archive whose members all left the Source is not listed again: keep its record as MovedAway, not Missing.
            if (run.Store is { } archives)
                foreach (var archivePath in run.FullyMovedArchives(source.Name))
                    await archives.RecordMovedAwayAsync(new FileKey(_settings.Destination, remotePath, source.Name, archivePath));
        }
    }

    private static MoveTargetConfig? TargetFor(FileEntry entry, AfterUploadConfig config)
    {
        MoveTargetConfig target;
        if (entry.Outcome == FileOutcome.Succeeded || (entry.Outcome == FileOutcome.Skipped && entry.Reason == UnchangedReason))
            target = config.OnSuccess;
        else if (entry.Outcome == FileOutcome.Failed && !IsChangedDuring(entry.Reason))
            target = config.OnFailure;
        else
            return null;
        return target.Action == MoveAction.Move ? target : null;
    }

    private static bool IsChangedDuring(string? reason) =>
        reason is not null && (reason.StartsWith("ChangedDuringUpload", StringComparison.Ordinal)
            || reason.StartsWith(ArchiveBuilder.ChangedDuringArchive, StringComparison.Ordinal));

    /// <summary>Null when there is nothing to move (the file has vanished).</summary>
    private async Task<MoveResult?> MoveOneAsync(ISource source, FileEntry entry, MoveTargetConfig target, CancellationToken ct)
    {
        try
        {
            // A file written to since the Run read it holds data that was never uploaded: leave it for the next Run.
            var now = await source.StatAsync(entry.Path, ct);
            if (now is null) return null;
            if (now.Size != entry.Size || now.ChangeToken != entry.ChangeToken)
                return MoveResult.Failed("it changed after it was read");
            return await source.MoveAsync(entry.Path, target, ct);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            return MoveResult.Failed(ex.Message);
        }
    }

    internal sealed partial class FileEntry
    {
        /// <summary>The <see cref="SourceFile.ChangeToken"/> the Run saw.</summary>
        public long ChangeToken { get; set; }
        /// <summary>The file left its Source through a Post-upload Move.</summary>
        public bool Moved { get; set; }
    }

    internal sealed partial class RunState
    {
        private int _movedAway;
        private int _moveFailures;
        public int MovedAway => Volatile.Read(ref _movedAway);
        public int MoveFailures => Volatile.Read(ref _moveFailures);
        internal void CountMoveFailure() => Interlocked.Increment(ref _moveFailures);

        /// <summary>This Run's own entries of a Source (not those carried over from earlier Runs), in path order.</summary>
        internal IReadOnlyList<FileEntry> OwnEntries(string source)
        {
            lock (_gate)
                return _entries.Where(kv => kv.Key.Source == source && !kv.Value.Carried)
                    .Select(kv => kv.Value.Clone())
                    .OrderBy(e => e.Path, StringComparer.Ordinal)
                    .ToList();
        }

        internal void MarkMoved(string source, string path)
        {
            lock (_gate)
                if (_entries.TryGetValue((source, path), out var entry)) entry.Moved = true;
            Interlocked.Increment(ref _movedAway);
        }

        /// <summary>Archives of the Source that were delivered and whose members have all been moved.</summary>
        internal IReadOnlyList<string> FullyMovedArchives(string source)
        {
            lock (_gate)
                return _archives.Where(kv => kv.Key.Source == source && kv.Value.Sha256 is not null)
                    .Where(kv => kv.Value.Members.All(m => _entries.TryGetValue((source, m), out var e) && e.Moved))
                    .Select(kv => kv.Key.Path)
                    .ToList();
        }
    }
}

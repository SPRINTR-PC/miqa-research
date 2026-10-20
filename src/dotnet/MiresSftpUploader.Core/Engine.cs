using System.Collections.Concurrent;
using System.Threading.Channels;
using Microsoft.Extensions.Logging;

namespace MiresSftpUploader.Core;

/// <summary>
/// Runs scan, hash, upload and Manifest upload over the configured Sources.
/// Per-file failures never throw; run-level failures come back as an exit code plus reason;
/// cancellation is caught here and reported as exit code 130.
/// </summary>
public sealed class Engine
{
    private readonly IRemote _remote;
    private readonly IReadOnlyList<ISource> _sources;
    private readonly EngineSettings _settings;
    private readonly ILogger<Engine> _logger;
    private readonly TimeProvider _time;

    public Engine(
        IRemote remote,
        IReadOnlyList<ISource> sources,
        EngineSettings settings,
        ILogger<Engine> logger,
        TimeProvider time)
    {
        _remote = remote;
        _sources = sources;
        _settings = settings;
        _logger = logger;
        _time = time;
    }

    public async Task<RunResult> RunAsync(RunOptions options, IProgress<RunEvent> progress, CancellationToken cancellationToken)
    {
        var run = new RunState(Guid.NewGuid(), _time.GetUtcNow(), progress);
        progress.Report(new RunStarted(run.RunId, run.StartedAt));
        _logger.LogInformation("Run {RunId} started by {User}", run.RunId, options.StartedBy);

        int exitCode;
        string? reason = null;
        try
        {
            (exitCode, reason) = await ExecuteAsync(options, run, cancellationToken);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            exitCode = ExitCodes.Cancelled;
            reason = "Cancelled";
        }

        var result = new RunResult(run.RunId, run.SnapshotCounts(), exitCode, reason);
        _logger.LogInformation("Run {RunId} finished with exit code {ExitCode}", run.RunId, exitCode);
        progress.Report(new RunFinished(result));
        return result;
    }

    private async Task<(int ExitCode, string? Reason)> ExecuteAsync(RunOptions options, RunState run, CancellationToken ct)
    {
        var unknown = options.SourceNames.Concat(options.ResetSources).FirstOrDefault(n => _sources.All(s => s.Name != n));
        if (unknown is not null) return (ExitCodes.ConfigurationError, $"Unknown Source '{unknown}'");

        if (options.DryRun || _settings.State.Path is not { Length: > 0 } databasePath)
            return await ExecuteCoreAsync(options, run, ct);

        using var runLock = RunLock.TryAcquire(databasePath + ".lock", options.StartedBy, _time.GetUtcNow(), out var holder);
        if (runLock is null) return (ExitCodes.LockHeld, $"Another Run holds the lock ({holder})");

        UploadStateStore store;
        try
        {
            store = UploadStateStore.Open(databasePath, _time);
        }
        catch (UploadStateTooNewException ex)
        {
            return (ExitCodes.ConfigurationError, ex.Message);
        }

        await using (store)
        {
            run.Store = store;
            await CleanUpAbandonedRunsAsync(store, ct);
            await store.BeginRunAsync(run.RunId, run.StartedAt, "Run", "Headless", options.StartedBy);
            using var heartbeat = _time.CreateTimer(
                _ => _ = store.HeartbeatAsync(run.RunId, _time.GetUtcNow()),
                null, _settings.State.HeartbeatInterval, _settings.State.HeartbeatInterval);

            (int ExitCode, string? Reason) outcome;
            try
            {
                outcome = await ExecuteCoreAsync(options, run, ct);
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested)
            {
                outcome = (ExitCodes.Cancelled, "Cancelled");
            }

            await heartbeat.DisposeAsync();
            var now = _time.GetUtcNow();
            await store.FinishRunAsync(run.RunId, now, outcome.ExitCode, run.SnapshotCounts());
            await store.PruneAsync(now, _settings.State.RunFilesRetention, _settings.State.MissingRetention);
            await store.FlushAsync();
            return outcome;
        }
    }

    /// <summary>Marks Runs with a stale heartbeat Abandoned and removes the .part files the state recorded for them.</summary>
    private async Task CleanUpAbandonedRunsAsync(UploadStateStore store, CancellationToken ct)
    {
        var orphans = await store.SweepAbandonedAsync(_time.GetUtcNow(), _settings.State.AbandonedAfter, _settings.Destination);
        if (orphans.Count == 0) return;

        var connect = await _remote.ConnectAsync(ct);
        if (!connect.IsOk)
        {
            _logger.LogWarning("Could not connect to clean up {Count} orphan .part files: {Reason}", orphans.Count, connect.Reason);
            return;
        }
        await using var session = connect.Value!;
        foreach (var orphan in orphans)
        {
            var deleted = await session.DeleteAsync(orphan.PartPath, ct);
            _logger.LogInformation("Abandoned Run: removed {Path}: {Result}", orphan.PartPath, deleted.IsOk ? "ok" : deleted.Reason);
        }
    }

    private async Task<(int ExitCode, string? Reason)> ExecuteCoreAsync(RunOptions options, RunState run, CancellationToken ct)
    {
        var selected = new List<ISource>();
        if (options.SourceNames.Count == 0)
            selected.AddRange(_sources);
        else
            foreach (var name in options.SourceNames)
            {
                var source = _sources.FirstOrDefault(s => s.Name == name);
                if (source is null) return (ExitCodes.ConfigurationError, $"Unknown Source '{name}'");
                selected.Add(source);
            }

        var work = new List<FileWork>();
        foreach (var source in selected)
        {
            var remotePath = RemotePathOf(source);
            var store = run.Store;
            if (store is not null && options.ResetSources.Contains(source.Name))
                await store.ResetSourceAsync(_settings.Destination, remotePath, source.Name);
            var prior = store?.LoadSource(_settings.Destination, remotePath, source.Name);
            var listed = new HashSet<string>(StringComparer.Ordinal);
            var rules = IgnoreRulesOf(source);
            await foreach (var file in source.ListAsync(ct))
            {
                listed.Add(file.RelativePath);
                PriorFile? known = null;
                prior?.TryGetValue(file.RelativePath, out known);
                var item = new FileWork(source, remotePath, file, options.RehashAll ? null : known);
                if (rules.Reason(file.RelativePath, m => run.Warn(m)) is { } ignored)
                    run.Set(item, FileOutcome.Ignored, ignored);
                else
                    work.Add(item);
            }
            if (store is not null)
                await store.MarkMissingAsync(_settings.Destination, remotePath, source.Name, listed, _time.GetUtcNow());
        }

        if (options.DryRun)
        {
            foreach (var item in work) run.Set(item, FileOutcome.Pending, null);
            return (ExitCodes.Ok, null);
        }

        foreach (var item in work) run.Set(item, FileOutcome.Pending, null);

        var channel = Channel.CreateUnbounded<FileWork>();
        foreach (var item in work) channel.Writer.TryWrite(item);
        channel.Writer.Complete();

        var workerCount = Math.Clamp(_settings.MaxParallelUploads, 1, Math.Max(work.Count, 1));
        var connectFailure = new ConcurrentQueue<string>();
        var workers = Enumerable.Range(0, workerCount)
            .Select(_ => WorkerAsync(channel.Reader, run, connectFailure, ct))
            .ToArray();
        await Task.WhenAll(workers);
        ct.ThrowIfCancellationRequested();

        if (connectFailure.TryPeek(out var failure))
            return (ExitCodes.ConnectFailed, failure);

        var connect = await _remote.ConnectAsync(ct);
        if (!connect.IsOk) return (ExitCodes.ConnectFailed, connect.Reason);
        await using (var session = connect.Value!)
        {
            foreach (var source in selected)
            {
                var uploaded = await UploadManifestAsync(session, source, run, ct);
                if (!uploaded.IsOk)
                    _logger.LogWarning("Manifest upload for Source {Source} failed: {Reason}", source.Name, uploaded.Reason);
            }
        }

        return run.Count(FileOutcome.Failed) > 0
            ? (ExitCodes.SomeFilesFailed, null)
            : (ExitCodes.Ok, null);
    }

    private async Task WorkerAsync(ChannelReader<FileWork> reader, RunState run, ConcurrentQueue<string> connectFailure, CancellationToken ct)
    {
        var connect = await _remote.ConnectAsync(ct);
        if (!connect.IsOk)
        {
            connectFailure.Enqueue(connect.Reason ?? "connect failed");
            // Drain so the other workers are not left with work nobody can do.
            await foreach (var _ in reader.ReadAllAsync(ct)) { }
            return;
        }

        await using var session = connect.Value!;
        await foreach (var item in reader.ReadAllAsync(ct))
        {
            ct.ThrowIfCancellationRequested();
            await ProcessAsync(session, item, run, ct);
        }
    }

    private async Task ProcessAsync(IRemoteSession session, FileWork item, RunState run, CancellationToken ct)
    {
        var store = run.Store;
        var key = item.Key(_settings.Destination);
        var mtime = item.File.Modified.UtcTicks;
        if (item.Prior is { Status: "Succeeded", Sha256: not null } prior
            && prior.Size == item.File.Size && prior.MtimeTicks == mtime)
        {
            run.Skip(item, prior.Sha256, "unchanged");
            store?.RecordSkipped(run.RunId, key, _time.GetUtcNow());
            return;
        }

        var started = _time.GetTimestamp();
        var max = Math.Max(_settings.Retry.MaxAttempts, 1);
        string failure = "";
        for (var attempt = 1; attempt <= max; attempt++)
        {
            run.Set(item, FileOutcome.Hashing, null);
            var attemptResult = await TryUploadAsync(session, item, run, ct);
            if (attemptResult.Sha256 is not null)
            {
                run.Succeed(item, attemptResult.Sha256);
                store?.RecordSucceeded(run.RunId, key, item.File.Size, mtime, attemptResult.Sha256, _time.GetUtcNow(), _time.GetElapsedTime(started));
                return;
            }

            failure = attemptResult.Reason ?? "unknown";
            _logger.LogWarning("Upload of {Source}/{Path} failed (attempt {Attempt}/{Max}): {Reason}",
                item.Source.Name, item.File.RelativePath, attempt, max, failure);
            if (attemptResult.Permanent) break;
            if (attempt < max) await Task.Delay(BackoffDelay(attempt), _time, ct);
        }

        run.Fail(item, failure);
        store?.RecordFailed(run.RunId, key, item.File.Size, mtime, failure, _time.GetUtcNow(), _time.GetElapsedTime(started));
    }

    private TimeSpan BackoffDelay(int attempt)
    {
        var retry = _settings.Retry;
        var exponential = retry.BaseDelay.TotalMilliseconds * Math.Pow(2, attempt - 1);
        var capped = Math.Min(exponential, retry.MaxDelay.TotalMilliseconds);
        var jittered = capped * (0.5 + Random.Shared.NextDouble() * 0.5);
        return TimeSpan.FromMilliseconds(jittered);
    }

    private async Task<UploadAttempt> TryUploadAsync(IRemoteSession session, FileWork item, RunState run, CancellationToken ct)
    {
        var finalPath = Join(item.RemotePath, item.File.RelativePath);
        var partPath = finalPath + ".part";
        try
        {
            var ensure = await session.EnsureDirectoryAsync(ParentOf(finalPath), ct);
            if (!ensure.IsOk) return UploadAttempt.From(ensure);

            if (run.Store is { } store)
                await store.MarkUploadingAsync(item.Key(_settings.Destination), item.File.Size, item.File.Modified.UtcTicks, partPath);

            string sha256;
            await using (var raw = await item.Source.OpenReadAsync(item.File.RelativePath, ct))
            await using (var hashing = new HashingReadStream(raw))
            {
                run.Set(item, FileOutcome.Uploading, null);
                var upload = await session.UploadAsync(hashing, partPath, ct);
                if (!upload.IsOk) return UploadAttempt.From(upload);
                sha256 = hashing.FinishHash();
            }

            var rename = await session.RenameAsync(partPath, finalPath, overwrite: true, ct);
            if (!rename.IsOk) return UploadAttempt.From(rename);
            return new UploadAttempt(sha256, null, false);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            return new UploadAttempt(null, ex.Message, false);
        }
    }

    private async Task<RemoteResult> UploadManifestAsync(IRemoteSession session, ISource source, RunState run, CancellationToken ct)
    {
        var remotePath = RemotePathOf(source);
        var finalPath = Join(remotePath, _settings.ManifestName);
        var json = ManifestWriter.Write(source.Name, run, run.StartedAt, _time.GetUtcNow(), run.SourceEntries(source.Name));

        var ensure = await session.EnsureDirectoryAsync(remotePath, ct);
        if (!ensure.IsOk) return ensure;
        using (var content = new MemoryStream(json))
        {
            var upload = await session.UploadAsync(content, finalPath + ".part", ct);
            if (!upload.IsOk) return upload;
        }
        return await session.RenameAsync(finalPath + ".part", finalPath, overwrite: true, ct);
    }

    private IgnoreRules IgnoreRulesOf(ISource source)
    {
        var own = _settings.SourceConfigs
            .FirstOrDefault(c => string.Equals(c.Name, source.Name, StringComparison.OrdinalIgnoreCase))?.Ignore;
        return new IgnoreRules(
            _settings.Ignore.UseDefaults,
            _settings.Ignore.Files.Concat(own?.Files ?? []),
            _settings.Ignore.Patterns.Concat(own?.Patterns ?? []));
    }

    private string RemotePathOf(ISource source) =>
        Normalize(source.RemotePath ?? Join(_settings.RemoteRoot, source.Name));

    private static string Normalize(string path)
    {
        var trimmed = path.Replace('\\', '/').TrimEnd('/');
        return trimmed.StartsWith('/') ? trimmed : "/" + trimmed;
    }

    private static string Join(string directory, string relative) =>
        directory.TrimEnd('/') + "/" + relative.TrimStart('/');

    private static string ParentOf(string path) => path[..path.LastIndexOf('/')] is { Length: > 0 } p ? p : "/";

    internal sealed record FileWork(ISource Source, string RemotePath, SourceFile File, PriorFile? Prior = null)
    {
        public FileKey Key(string destination) => new(destination, RemotePath, Source.Name, File.RelativePath);
    }

    private sealed record UploadAttempt(string? Sha256, string? Reason, bool Permanent)
    {
        public static UploadAttempt From(RemoteResult failed) =>
            failed.Kind == RemoteResultKind.Denied
                ? new UploadAttempt(null, "RemoteDenied: " + failed.Reason, true)
                : new UploadAttempt(null, failed.Reason, false);
    }

    /// <summary>Mutable state of one Run: outcome per file, hashes and failures for the Manifest.</summary>
    internal sealed class RunState(Guid runId, DateTimeOffset startedAt, IProgress<RunEvent> progress)
    {
        private readonly object _gate = new();
        private readonly Dictionary<(string Source, string Path), FileEntry> _entries = new();

        public Guid RunId { get; } = runId;
        public DateTimeOffset StartedAt { get; } = startedAt;
        public UploadStateStore? Store { get; set; }

        internal void Warn(string message) => progress.Report(new RunWarning(message));

        internal void Set(FileWork item, FileOutcome outcome, string? reason) =>
            Update(item, e => { e.Outcome = outcome; e.Reason = reason; });

        internal void Succeed(FileWork item, string sha256) =>
            Update(item, e => { e.Outcome = FileOutcome.Succeeded; e.Reason = null; e.Sha256 = sha256; });

        internal void Skip(FileWork item, string sha256, string reason) =>
            Update(item, e => { e.Outcome = FileOutcome.Skipped; e.Reason = reason; e.Sha256 = sha256; });

        internal void Fail(FileWork item, string reason) =>
            Update(item, e => { e.Outcome = FileOutcome.Failed; e.Reason = reason; });

        private void Update(FileWork item, Action<FileEntry> change)
        {
            FileEntry entry;
            lock (_gate)
            {
                var key = (item.Source.Name, item.File.RelativePath);
                if (!_entries.TryGetValue(key, out entry!))
                    _entries[key] = entry = new FileEntry(item.File.RelativePath, item.File.Size);
                change(entry);
            }
            progress.Report(new FileOutcomeChanged(item.Source.Name, item.File.RelativePath, entry.Outcome, entry.Reason));
        }

        public int Count(FileOutcome outcome)
        {
            lock (_gate) return _entries.Values.Count(e => e.Outcome == outcome);
        }

        public IReadOnlyDictionary<FileOutcome, int> SnapshotCounts()
        {
            lock (_gate)
                return _entries.Values.GroupBy(e => e.Outcome).ToDictionary(g => g.Key, g => g.Count());
        }

        public IReadOnlyList<FileEntry> SourceEntries(string source)
        {
            lock (_gate)
                return _entries.Where(kv => kv.Key.Source == source)
                    .Select(kv => kv.Value.Clone())
                    .OrderBy(e => e.Path, StringComparer.Ordinal)
                    .ToList();
        }
    }

    internal sealed class FileEntry(string path, long size)
    {
        public string Path { get; } = path;
        public long Size { get; } = size;
        public FileOutcome Outcome { get; set; }
        public string? Reason { get; set; }
        public string? Sha256 { get; set; }

        public FileEntry Clone() => new(Path, Size) { Outcome = Outcome, Reason = Reason, Sha256 = Sha256 };
    }
}

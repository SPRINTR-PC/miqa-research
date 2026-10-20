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
        var run = new RunState(Guid.NewGuid(), _time.GetUtcNow(), progress, _logger);
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
        WriteReport(options, run, result);
        _logger.LogInformation("Run {RunId} finished: Succeeded {Succeeded}, Skipped {Skipped}, Failed {Failed}, exit code {ExitCode}",
            run.RunId, result.Count(FileOutcome.Succeeded), result.Count(FileOutcome.Skipped), result.Count(FileOutcome.Failed), exitCode);
        progress.Report(new RunFinished(result));
        return result;
    }

    private static string ModeOf(RunOptions options) =>
        options.DryRun ? "DryRun" : options.RetryOf is not null ? "Retry" : "Run";

    /// <summary>Writes the Report of the Run, whatever its exit code. A Report that cannot be written is logged, never a Run failure.</summary>
    private void WriteReport(RunOptions options, RunState run, RunResult result)
    {
        var format = options.ReportFormat ?? _settings.Report.Format;
        var now = _time.GetUtcNow();
        var path = ReportPathFor(options, run, format);
        if (path is null) return;

        var counts = result.Counts.ToDictionary(kv => kv.Key.ToString(), kv => kv.Value);
        var summary = new RunSummary(run.RunId, "Finished", result.ExitCode, options.StartedBy, ModeOf(options),
            options.Trigger.ToString(), run.StartedAt, now, now, false, counts);
        var files = run.SnapshotFiles().Select(e => new RunFileOutcome(e.Source, e.Path, e.Outcome.ToString(), e.Bytes, e.DurationMs, e.Reason)).ToList();
        try
        {
            ReportWriter.WriteFile(path, ReportWriter.Render(new RunDetail(summary, files), format));
            _logger.LogInformation("Report written to {Path}", path);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            _logger.LogWarning("Could not write the Report to {Path}: {Reason}", path, ex.Message);
        }
    }

    private string? ReportPathFor(RunOptions options, RunState run, ReportFormat format)
    {
        var name = ReportWriter.FileName(_settings.Report.FileNamePattern, run.RunId, run.StartedAt, format);
        if (options.ReportPath is { Length: > 0 } explicitPath)
            return Directory.Exists(explicitPath) || explicitPath.EndsWith('/') || explicitPath.EndsWith('\\')
                ? Path.Combine(explicitPath, name)
                : explicitPath;
        if (options.DryRun) return null;
        var directory = _settings.Report.Directory
            ?? (_settings.State.Path is { Length: > 0 } db ? Path.Combine(Path.GetDirectoryName(Path.GetFullPath(db))!, "reports") : null);
        return directory is null ? null : Path.Combine(directory, name);
    }

    private async Task<(int ExitCode, string? Reason)> ExecuteAsync(RunOptions options, RunState run, CancellationToken ct)
    {
        var unknown = options.SourceNames.Concat(options.ResetSources).FirstOrDefault(n => _sources.All(s => s.Name != n));
        if (unknown is not null) return (ExitCodes.ConfigurationError, $"Unknown Source '{unknown}'");

        if (options.RetryOf is not null && (options.DryRun || _settings.State.Path is not { Length: > 0 }))
            return (ExitCodes.ConfigurationError, "Retrying a Run needs the Upload State");

        if (options.DryRun || _settings.State.Path is not { Length: > 0 } databasePath)
            return await ExecuteCoreAsync(options, run, ct);

        var access = EnsureDataDirectory(databasePath, run);
        if (access.Problem is not null) return (ExitCodes.ConfigurationError, access.Problem);

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
            if (options.RetryOf is { } retryOf && !store.RunExists(retryOf))
                return (ExitCodes.ConfigurationError, $"Unknown Run {retryOf}");
            await CleanUpAbandonedRunsAsync(store, ct);
            await store.BeginRunAsync(run.RunId, run.StartedAt, ModeOf(options), options.Trigger.ToString(), options.StartedBy);
            using var cancelRequested = CancellationTokenSource.CreateLinkedTokenSource(ct);
            using var heartbeat = _time.CreateTimer(
                _ => _ = store.HeartbeatAsync(run.RunId, _time.GetUtcNow()),
                null, _settings.State.HeartbeatInterval, _settings.State.HeartbeatInterval);
            // Another account (or process) can ask this Run to stop through the Upload State.
            using var cancelPoll = _time.CreateTimer(
                _ => PollCancelRequest(store, run.RunId, cancelRequested),
                null, _settings.State.CancelPollInterval, _settings.State.CancelPollInterval);

            (int ExitCode, string? Reason) outcome;
            try
            {
                outcome = await ExecuteCoreAsync(options, run, cancelRequested.Token);
            }
            catch (OperationCanceledException) when (cancelRequested.IsCancellationRequested)
            {
                outcome = (ExitCodes.Cancelled, "Cancelled");
            }

            await cancelPoll.DisposeAsync();
            await heartbeat.DisposeAsync();
            var now = _time.GetUtcNow();
            await store.FinishRunAsync(run.RunId, now, outcome.ExitCode, run.SnapshotCounts());
            await store.PruneAsync(now, _settings.State.RunFilesRetention, _settings.State.MissingRetention);
            await store.FlushAsync();
            return outcome;
        }
    }

    /// <summary>
    /// Checks the Data Directory holding the Upload State and reports the result. A missing directory is set up first when
    /// this account has the rights; otherwise the problem (path, account, fix command) is returned. Never falls back to another directory.
    /// </summary>
    private DataDirectoryAccess EnsureDataDirectory(string databasePath, RunState run)
    {
        var directory = Path.GetDirectoryName(Path.GetFullPath(databasePath))!;
        if (!Directory.Exists(directory))
        {
            var init = DataDirectory.Initialize(directory, _settings.State.AccessGroup, DataDirectory.CurrentPlatform);
            foreach (var action in init.Actions) _logger.LogInformation("Data Directory: {Action}", action);
            if (!init.Ok) _logger.LogWarning("Data Directory could not be set up: {Error}", init.Error);
        }

        var access = DataDirectory.Check(directory);
        run.Report(new DataDirectoryChecked(access));
        if (access.OnNetworkShare)
            run.Warn($"The Data Directory '{directory}' looks like a network share. SQLite locking is unreliable there; use a local directory.");
        return access;
    }

    private void PollCancelRequest(UploadStateStore store, Guid runId, CancellationTokenSource cancel)
    {
        try
        {
            if (store.IsCancelRequested(runId)) cancel.Cancel();
        }
        catch (Exception ex) when (ex is Microsoft.Data.Sqlite.SqliteException or ObjectDisposedException)
        {
            _logger.LogWarning("Could not read the cancel request of Run {RunId}: {Reason}", runId, ex.Message);
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
        await store.ForgetOrphansAsync(_settings.Destination);
    }

    /// <summary>
    /// Plans a retry without scanning: only the files that failed in the given Run and are still Failed in the Upload State.
    /// A vanished file becomes Missing. Everything else the Upload State knows as delivered is carried into the Manifest.
    /// Returns the Sources that take part.
    /// </summary>
    private async Task<List<ISource>> PlanRetryAsync(Guid retryOf, List<ISource> candidates, List<FileWork> work, RunState run, CancellationToken ct)
    {
        var store = run.Store!;
        var failedInRun = store.LoadFailedOf(retryOf, _settings.Destination);
        var participating = new List<ISource>();
        foreach (var source in candidates)
        {
            var remotePath = RemotePathOf(source);
            var failedPaths = failedInRun.Where(f => f.Source == source.Name && f.RemotePath == remotePath).Select(f => f.RelativePath).ToHashSet(StringComparer.Ordinal);
            if (failedPaths.Count == 0) continue;
            participating.Add(source);

            var prior = store.LoadSource(_settings.Destination, remotePath, source.Name);
            foreach (var (path, known) in prior.OrderBy(kv => kv.Key, StringComparer.Ordinal))
            {
                if (known.Status == "Succeeded" && known.Sha256 is not null)
                    run.Carry(source.Name, path, known.Size, known.Sha256);
                if (known.Status != "Failed" || !failedPaths.Contains(path)) continue;

                var stat = await source.StatAsync(path, ct);
                if (stat is null)
                {
                    var key = new FileKey(_settings.Destination, remotePath, source.Name, path);
                    var vanished = new FileWork(source, remotePath, new SourceFile(path, known.Size, new DateTimeOffset(known.MtimeTicks, TimeSpan.Zero)));
                    run.Set(vanished, FileOutcome.Skipped, "Missing");
                    store.RecordSkipped(run.RunId, key, _time.GetUtcNow(), "Missing");
                    await store.MarkMissingFileAsync(key, _time.GetUtcNow());
                    continue;
                }
                work.Add(new FileWork(source, remotePath, stat));
            }
        }
        return participating;
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
        if (options.RetryOf is { } retryOf)
        {
            selected = await PlanRetryAsync(retryOf, selected, work, run, ct);
        }
        else
        foreach (var source in selected)
        {
            var remotePath = RemotePathOf(source);
            var store = run.Store;
            if (store is not null && options.ResetSources.Contains(source.Name))
                await store.ResetSourceAsync(_settings.Destination, remotePath, source.Name);
            var prior = store?.LoadSource(_settings.Destination, remotePath, source.Name);
            if (options.DryRun && _settings.State.Path is { Length: > 0 } dryRunDatabase)
                prior = UploadStateStore.ReadPriorFiles(dryRunDatabase, _settings.Destination, remotePath, source.Name);
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
                else if (IsTooRecent(source, file))
                    run.Set(item, FileOutcome.Skipped, TooRecentReason);
                else
                    work.Add(item);
            }
            if (store is not null)
                await store.MarkMissingAsync(_settings.Destination, remotePath, source.Name, listed, _time.GetUtcNow());
        }

        if (options.DryRun)
        {
            foreach (var item in work)
            {
                if (IsUnchanged(item, out var prior)) run.Skip(item, prior.Sha256!, UnchangedReason);
                else run.Set(item, FileOutcome.Pending, null);
            }
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
        if (IsUnchanged(item, out var prior))
        {
            run.Skip(item, prior.Sha256!, UnchangedReason);
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
                run.Succeed(item, attemptResult.Sha256, _time.GetElapsedTime(started));
                store?.RecordSucceeded(run.RunId, key, item.File.Size, mtime, attemptResult.Sha256, _time.GetUtcNow(), _time.GetElapsedTime(started));
                return;
            }

            failure = attemptResult.Reason ?? "unknown";
            _logger.LogWarning("Upload of {Source}/{Path} failed (attempt {Attempt}/{Max}): {Reason}",
                item.Source.Name, item.File.RelativePath, attempt, max, failure);
            if (attemptResult.Permanent) break;
            if (attempt < max) await Task.Delay(BackoffDelay(attempt), _time, ct);
        }

        run.Fail(item, failure, _time.GetElapsedTime(started));
        store?.RecordFailed(run.RunId, key, item.File.Size, mtime, failure, _time.GetUtcNow(), _time.GetElapsedTime(started));
    }

    private const string UnchangedReason = "unchanged";

    /// <summary>The size and mtime fast path: the Upload State has this file Succeeded with the same size and mtime.</summary>
    private static bool IsUnchanged(FileWork item, out PriorFile prior)
    {
        prior = item.Prior!;
        return item.Prior is { Status: "Succeeded", Sha256: not null } known
            && known.Size == item.File.Size && known.MtimeTicks == item.File.Modified.UtcTicks;
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
            long bytesRead;
            await using (var raw = await item.Source.OpenReadAsync(item.File.RelativePath, ct))
            await using (var hashing = new HashingReadStream(raw))
            {
                run.Set(item, FileOutcome.Uploading, null);
                var upload = await session.UploadAsync(hashing, partPath, ct);
                if (!upload.IsOk) return UploadAttempt.From(upload);
                sha256 = hashing.FinishHash();
                bytesRead = hashing.BytesRead;
            }

            // A file that changed while it was read has a hash that matches no version of it: never rename it into place.
            var changed = await ChangedSinceListingAsync(item, bytesRead, ct);
            if (changed is not null)
            {
                await session.DeleteAsync(partPath, ct);
                return new UploadAttempt(null, "ChangedDuringUpload: " + changed, true);
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

    /// <summary>Why the file no longer matches its listing, or null when it is unchanged.</summary>
    private static async Task<string?> ChangedSinceListingAsync(FileWork item, long bytesRead, CancellationToken ct)
    {
        var listed = item.File;
        if (bytesRead != listed.Size) return $"read {bytesRead} bytes, listed {listed.Size}";
        var now = await item.Source.StatAsync(listed.RelativePath, ct);
        if (now is null) return null;
        if (now.Size != listed.Size) return $"size is now {now.Size}, listed {listed.Size}";
        if (now.Modified.UtcTicks != listed.Modified.UtcTicks) return $"modified at {now.Modified:O}, listed {listed.Modified:O}";
        return null;
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

    internal const string TooRecentReason = "TooRecent";

    /// <summary>Too Recent: modified less than the minimum age ago, or at or after the cutoff. A Source's own setting replaces the global one.</summary>
    private bool IsTooRecent(ISource source, SourceFile file)
    {
        var own = _settings.SourceConfigs
            .FirstOrDefault(c => string.Equals(c.Name, source.Name, StringComparison.OrdinalIgnoreCase))?.Scan;
        var minAge = own?.MinFileAgeSeconds ?? _settings.Scan.MinFileAgeSeconds;
        var cutoff = own?.ModifiedBefore ?? _settings.Scan.ModifiedBefore;
        if (minAge > 0 && file.Modified > _time.GetUtcNow() - TimeSpan.FromSeconds(minAge)) return true;
        return cutoff is { } limit && file.Modified >= limit;
    }

    private IgnoreRules IgnoreRulesOf(ISource source)
    {
        var own = _settings.SourceConfigs
            .FirstOrDefault(c => string.Equals(c.Name, source.Name, StringComparison.OrdinalIgnoreCase))?.Ignore;
        return new IgnoreRules(
            _settings.Ignore.UseDefaults,
            _settings.Ignore.Files.Concat(own?.Files ?? []),
            _settings.Ignore.Patterns.Concat(own?.Patterns ?? []),
            alwaysPaths: [_settings.ManifestName, _settings.ManifestName + ".part", _settings.FlatManifestName, _settings.FlatManifestName + ".part"],
            alwaysNames: UploadStateFileNames());
    }

    /// <summary>The Upload State database and the files SQLite keeps beside it, plus the Run lock.</summary>
    private IEnumerable<string> UploadStateFileNames()
    {
        if (_settings.State.Path is not { Length: > 0 } path) return [];
        var name = Path.GetFileName(path);
        return [name, name + "-wal", name + "-shm", name + "-journal", name + ".lock"];
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
    internal sealed class RunState(Guid runId, DateTimeOffset startedAt, IProgress<RunEvent> progress, ILogger logger)
    {
        private readonly object _gate = new();
        private readonly Dictionary<(string Source, string Path), FileEntry> _entries = new();

        public Guid RunId { get; } = runId;
        public DateTimeOffset StartedAt { get; } = startedAt;
        public UploadStateStore? Store { get; set; }

        internal void Report(RunEvent runEvent) => progress.Report(runEvent);
        /// <summary>A file delivered by an earlier Run, listed in the Manifest but not an outcome of this Run.</summary>
        internal void Carry(string source, string path, long size, string sha256)
        {
            lock (_gate)
                _entries[(source, path)] = new FileEntry(source, path, size) { Outcome = FileOutcome.Skipped, Reason = "delivered earlier", Sha256 = sha256, Carried = true };
        }

        internal void Warn(string message) => progress.Report(new RunWarning(message));

        internal void Set(FileWork item, FileOutcome outcome, string? reason) =>
            Update(item, e => { e.Outcome = outcome; e.Reason = reason; });

        internal void Succeed(FileWork item, string sha256, TimeSpan duration) =>
            Update(item, e => { e.Outcome = FileOutcome.Succeeded; e.Reason = null; e.Sha256 = sha256; e.Bytes = e.Size; e.DurationMs = (long)duration.TotalMilliseconds; });

        internal void Skip(FileWork item, string sha256, string reason) =>
            Update(item, e => { e.Outcome = FileOutcome.Skipped; e.Reason = reason; e.Sha256 = sha256; });

        internal void Fail(FileWork item, string reason, TimeSpan duration) =>
            Update(item, e => { e.Outcome = FileOutcome.Failed; e.Reason = reason; e.DurationMs = (long)duration.TotalMilliseconds; });

        private void Update(FileWork item, Action<FileEntry> change)
        {
            FileEntry entry;
            lock (_gate)
            {
                var key = (item.Source.Name, item.File.RelativePath);
                if (!_entries.TryGetValue(key, out entry!))
                    _entries[key] = entry = new FileEntry(item.Source.Name, item.File.RelativePath, item.File.Size);
                change(entry);
            }
            LogFinalOutcome(item, entry);
            progress.Report(new FileOutcomeChanged(item.Source.Name, item.File.RelativePath, entry.Outcome, entry.Reason));
        }

        /// <summary>Info for a file that ended Succeeded or Skipped, Error for one that Failed. Intermediate outcomes are not logged.</summary>
        private void LogFinalOutcome(FileWork item, FileEntry entry)
        {
            switch (entry.Outcome)
            {
                case FileOutcome.Succeeded:
                    logger.LogInformation("{Source}/{Path}: Succeeded", item.Source.Name, item.File.RelativePath);
                    break;
                case FileOutcome.Skipped:
                    logger.LogInformation("{Source}/{Path}: Skipped ({Reason})", item.Source.Name, item.File.RelativePath, entry.Reason);
                    break;
                case FileOutcome.Failed:
                    logger.LogError("{Source}/{Path}: Failed ({Reason})", item.Source.Name, item.File.RelativePath, entry.Reason);
                    break;
            }
        }

        public int Count(FileOutcome outcome)
        {
            lock (_gate) return _entries.Values.Count(e => !e.Carried && e.Outcome == outcome);
        }

        public IReadOnlyDictionary<FileOutcome, int> SnapshotCounts()
        {
            lock (_gate)
                return _entries.Values.Where(e => !e.Carried).GroupBy(e => e.Outcome).ToDictionary(g => g.Key, g => g.Count());
        }

        public IReadOnlyList<FileEntry> SnapshotFiles()
        {
            lock (_gate)
                return _entries.Values.Where(e => !e.Carried).Select(e => e.Clone())
                    .OrderBy(e => e.Source, StringComparer.Ordinal).ThenBy(e => e.Path, StringComparer.Ordinal).ToList();
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

    internal sealed class FileEntry(string source, string path, long size)
    {
        public string Source { get; } = source;
        public bool Carried { get; set; }
        public long Bytes { get; set; }
        public long DurationMs { get; set; }
        public string Path { get; } = path;
        public long Size { get; } = size;
        public FileOutcome Outcome { get; set; }
        public string? Reason { get; set; }
        public string? Sha256 { get; set; }

        public FileEntry Clone() => new(Source, Path, Size) { Outcome = Outcome, Reason = Reason, Sha256 = Sha256, Bytes = Bytes, DurationMs = DurationMs, Carried = Carried };
    }
}

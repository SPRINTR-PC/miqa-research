using System.Collections.Concurrent;
using System.Threading.Channels;
using Microsoft.Extensions.Logging;

namespace MiresSftpUploader.Core;

/// <summary>
/// Runs scan, hash, upload and Manifest upload over the configured Sources.
/// Per-file failures never throw; run-level failures come back as an exit code plus reason;
/// cancellation is caught here and reported as exit code 130.
/// </summary>
public sealed partial class Engine : IRunEngine
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
        finally
        {
            DeleteStagingArea(run);
        }

        var result = new RunResult(run.RunId, run.SnapshotCounts(), exitCode, reason, run.Verified, run.VerificationFailures);
        result = result with { ReportPath = WriteReport(options, run, result) };
        _logger.LogInformation("Run {RunId} finished: Succeeded {Succeeded}, Skipped {Skipped}, Failed {Failed}, exit code {ExitCode}",
            run.RunId, result.Count(FileOutcome.Succeeded), result.Count(FileOutcome.Skipped), result.Count(FileOutcome.Failed), exitCode);
        progress.Report(new RunFinished(result));
        return result;
    }

    private static string ModeOf(RunOptions options) =>
        options.DryRun ? "DryRun" : options.RetryOf is not null ? "Retry" : "Run";

    /// <summary>Writes the Report of the Run, whatever its exit code. A Report that cannot be written is logged, never a Run failure.</summary>
    private string? WriteReport(RunOptions options, RunState run, RunResult result)
    {
        var format = options.ReportFormat ?? _settings.Report.Format;
        var now = _time.GetUtcNow();
        var path = ReportPathFor(options, run, format);
        if (path is null) return null;

        var counts = result.Counts.ToDictionary(kv => kv.Key.ToString(), kv => kv.Value);
        if (result.Verified > 0) counts["Verified"] = result.Verified;
        if (result.VerificationFailures > 0) counts["VerificationFailed"] = result.VerificationFailures;
        var summary = new RunSummary(run.RunId, "Finished", result.ExitCode, options.StartedBy, ModeOf(options),
            options.Trigger.ToString(), run.StartedAt, now, now, false, counts);
        var files = run.SnapshotFiles().Select(e => new RunFileOutcome(e.Source, e.Path, e.Outcome.ToString(), e.Bytes, e.DurationMs, e.Reason)).ToList();
        try
        {
            ReportWriter.WriteFile(path, ReportWriter.Render(new RunDetail(summary, files), format));
            _logger.LogInformation("Report written to {Path}", path);
            return path;
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            _logger.LogWarning("Could not write the Report to {Path}: {Reason}", path, ex.Message);
            return null;
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
            RemoveStaleStagingAreas(run);
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
        if (_settings.RemoteAccess == RemoteAccess.WriteOnly)
        {
            _logger.LogInformation("Abandoned Run: left {Count} .part files on the server; the account cannot delete", orphans.Count);
            await store.ForgetOrphansAsync(_settings.Destination);
            return;
        }

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
    private async Task<List<ISource>> PlanRetryAsync(Guid retryOf, List<ISource> candidates, List<object> work, RunState run, CancellationToken ct)
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
            var priorArchives = store.LoadArchives(_settings.Destination, remotePath, source.Name);
            var maybeArchives = new List<(string Path, PriorFile Known)>();
            foreach (var (path, known) in prior.OrderBy(kv => kv.Key, StringComparer.Ordinal))
            {
                if (known.Status == "Succeeded" && known.Sha256 is not null)
                {
                    if (priorArchives.TryGetValue(path, out var delivered)) run.CarryArchive(source.Name, path, known.Size, known.Sha256, delivered.Members);
                    else run.Carry(source.Name, path, known.Size, known.Sha256);
                }
                if (known.Status != "Failed" || !failedPaths.Contains(path)) continue;

                var stat = await source.StatAsync(path, ct);
                if (stat is null) maybeArchives.Add((path, known));
                else work.Add(new FileWork(source, remotePath, stat));
            }

            // A failed path that is not a file of the Source may be an Archive: plan the Source to find out.
            var rebuilt = new HashSet<string>(StringComparer.Ordinal);
            if (maybeArchives.Count > 0 && ArchiveRulesOf(source).Count > 0)
                foreach (var archive in await PlanArchivesAsync(source, remotePath, run, ct))
                {
                    if (!maybeArchives.Any(m => m.Path == archive.RelativePath)) continue;
                    rebuilt.Add(archive.RelativePath);
                    var archiveWork = new ArchiveWork(source, remotePath, archive, Prior: null);
                    if (PlanArchive(archiveWork, run, dryRun: false)) work.Add(archiveWork);
                }
            foreach (var (path, known) in maybeArchives.Where(m => !rebuilt.Contains(m.Path)))
            {
                var key = new FileKey(_settings.Destination, remotePath, source.Name, path);
                var vanished = new FileWork(source, remotePath, new SourceFile(path, known.Size, new DateTimeOffset(known.MtimeTicks, TimeSpan.Zero)));
                run.Set(vanished, FileOutcome.Skipped, "Missing");
                store.RecordSkipped(run.RunId, key, _time.GetUtcNow(), "Missing");
                await store.MarkMissingFileAsync(key, _time.GetUtcNow());
            }
        }
        return participating;
    }

    /// <summary>
    /// Settles whether this Run has Write-only Access: as configured, or for <c>Auto</c> by trying to stat and list the Remote Root
    /// (a refusal means write-only). The result is logged. A Dry Run touches nothing, so it only honours an explicit setting.
    /// </summary>
    private async Task<(int ExitCode, string? Reason)?> ResolveRemoteAccessAsync(RunOptions options, RunState run, CancellationToken ct)
    {
        switch (_settings.RemoteAccess)
        {
            case RemoteAccess.WriteOnly:
                run.WriteOnly = true;
                run.WriteOnlyReason = "RemoteAccess is WriteOnly";
                _logger.LogInformation("Remote access: write-only (configured); read-based checks are off");
                return null;
            case RemoteAccess.ReadWrite:
                _logger.LogInformation("Remote access: read-write (configured)");
                return null;
        }
        if (options.DryRun) return null;

        var connect = await _remote.ConnectAsync(ct);
        if (!connect.IsOk) return (ExitCodes.ConnectFailed, connect.Reason);
        await using var session = connect.Value!;
        var root = Normalize(_settings.RemoteRoot);
        var ensure = await session.EnsureDirectoryAsync(root, ct);
        if (!ensure.IsOk)
        {
            _logger.LogInformation("Remote access: read-write assumed; could not prepare {Root}: {Reason}", root, ensure.Reason);
            return null;
        }
        var stat = await session.StatAsync(root, ct);
        var list = await session.ListAsync(root, ct);
        var denied = stat.Kind == RemoteResultKind.Denied ? stat.Reason : list.Kind == RemoteResultKind.Denied ? list.Reason : null;
        if (denied is null)
        {
            _logger.LogInformation("Remote access: read-write (stat and listing of {Root} work)", root);
            return null;
        }
        run.WriteOnly = true;
        run.WriteOnlyReason = denied;
        _logger.LogInformation("Remote access: write-only (detected: {Reason}); read-based checks are off", denied);
        return null;
    }

    /// <summary>Verification reads from the server, which a write-only account cannot do: exit 2 rather than silently skipping it.</summary>
    private (int ExitCode, string? Reason)? WriteOnlyVerificationConflict(RunState run)
    {
        if (!run.WriteOnly) return null;
        var settings = _settings.Verification;
        var (setting, level) = settings.AfterUpload != VerificationLevel.Off ? ("Upload:VerifyAfterUpload", settings.AfterUpload)
            : settings.Remote != VerificationLevel.Off ? ("Upload:VerifyRemote", settings.Remote) : (null, VerificationLevel.Off);
        return setting is null
            ? null
            : (ExitCodes.ConfigurationError, $"{setting} is {level}, which this server cannot do: the account has Write-only Access ({run.WriteOnlyReason}) and Verification reads from the server. Turn Verification off.");
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

        run.BuildGate = new SemaphoreSlim(Math.Max(_settings.Archive.MaxParallelBuilds, 1));
        if (await ResolveRemoteAccessAsync(options, run, ct) is { } accessFailure) return accessFailure;
        var work = new List<object>();
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
            var priorArchives = store?.LoadArchives(_settings.Destination, remotePath, source.Name);
            if (options.DryRun && _settings.State.Path is { Length: > 0 } archiveDatabase)
                priorArchives = UploadStateStore.ReadPriorArchives(archiveDatabase, _settings.Destination, remotePath, source.Name);
            var listed = new HashSet<string>(StringComparer.Ordinal);
            var rules = IgnoreRulesOf(source);
            var reserved = ReservedManifestNames();
            var collisions = new List<string>();
            var candidates = new List<(FileWork Item, bool TooRecent)>();
            await foreach (var file in source.ListAsync(ct))
            {
                listed.Add(file.RelativePath);
                PriorFile? known = null;
                prior?.TryGetValue(file.RelativePath, out known);
                var item = new FileWork(source, remotePath, file, options.RehashAll ? null : known);
                if (rules.Reason(file.RelativePath, m => run.Warn(m)) is { } ignored)
                    run.Set(item, FileOutcome.Ignored, ignored);
                else if (!run.WriteOnly && reserved.Contains(file.RelativePath))
                    collisions.Add(file.RelativePath);
                else
                    candidates.Add((item, IsTooRecent(source, file)));
            }
            if (collisions.Count > 0)
                return (ExitCodes.ConfigurationError,
                    $"Source '{source.Name}' holds {string.Join(", ", collisions.Select(c => $"'{c}'"))}, which the Manifest would overwrite. Rename the file, ignore it, or change the Manifest names.");

            var plan = ArchivePlanner.Plan(ArchiveRulesOf(source), candidates, source.Name, run.StartedAt);
            foreach (var (item, tooRecent) in plan.Individual)
            {
                if (tooRecent) run.Set(item, FileOutcome.Skipped, TooRecentReason);
                else work.Add(item);
            }
            foreach (var archive in plan.Archives)
            {
                listed.Add(archive.RelativePath);
                PriorArchive? priorArchive = null;
                priorArchives?.TryGetValue(archive.RelativePath, out priorArchive);
                var archiveWork = new ArchiveWork(source, remotePath, archive, options.RehashAll ? null : priorArchive);
                if (PlanArchive(archiveWork, run, options.DryRun)) work.Add(archiveWork);
            }
            if (store is not null)
                await store.MarkMissingAsync(_settings.Destination, remotePath, source.Name, listed, _time.GetUtcNow());
        }

        if (options.DryRun)
        {
            foreach (var item in work.OfType<FileWork>())
            {
                if (IsUnchanged(item, out var prior)) run.Skip(item, prior.Sha256!, UnchangedReason);
                else run.Set(item, FileOutcome.Pending, null);
            }
            return (ExitCodes.Ok, null);
        }

        if (WriteOnlyVerificationConflict(run) is { } conflict) return conflict;
        if (await ProbeVerificationAsync(ct) is { } unavailable) return unavailable;

        foreach (var item in work.OfType<FileWork>()) run.Set(item, FileOutcome.Pending, null);

        var markers = await PlaceMarkersAsync(selected, run, ct);

        var channel = Channel.CreateUnbounded<object>();
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
                var uploaded = await UploadManifestAsync(session, source, run, options, ct);
                if (!uploaded.IsOk)
                    _logger.LogWarning("Manifest upload for Source {Source} failed: {Reason}", source.Name, uploaded.Reason);
            }
            // After the Manifests, so a consumer that sees no Marker finds the final Manifest.
            foreach (var marker in markers)
            {
                var removed = await session.DeleteAsync(marker, ct);
                if (!removed.IsOk) _logger.LogWarning("Could not remove the In-progress Marker {Path}: {Reason}", marker, removed.Reason);
            }
        }

        return run.Count(FileOutcome.Failed) > 0
            ? (ExitCodes.SomeFilesFailed, null)
            : (ExitCodes.Ok, null);
    }

    /// <summary>
    /// Puts the In-progress Marker next to each Source's Manifest so consumers know the Manifest may be stale. A Marker nobody
    /// could remove would lie forever, so one is only placed after a probe file proves the account can delete.
    /// Returns the server paths of the Markers to remove at the end of the Run.
    /// </summary>
    private async Task<List<string>> PlaceMarkersAsync(IReadOnlyList<ISource> sources, RunState run, CancellationToken ct)
    {
        var placed = new List<string>();
        if (run.WriteOnly)
        {
            _logger.LogInformation("No In-progress Markers: the account has Write-only Access and cannot remove them");
            return placed;
        }
        var connect = await _remote.ConnectAsync(ct);
        if (!connect.IsOk)
        {
            _logger.LogWarning("No In-progress Markers: could not connect: {Reason}", connect.Reason);
            return placed;
        }

        await using var session = connect.Value!;
        foreach (var source in sources)
        {
            var remotePath = RemotePathOf(source);
            var marker = Join(remotePath, _settings.ManifestName + _settings.InProgressSuffix);
            var probe = marker + ".probe";
            var ensure = await session.EnsureDirectoryAsync(remotePath, ct);
            if (!ensure.IsOk) continue;

            using (var content = new MemoryStream())
            {
                if (!(await session.UploadAsync(content, probe, ct)).IsOk) continue;
            }
            if (!(await session.DeleteAsync(probe, ct)).IsOk)
            {
                _logger.LogInformation("No In-progress Marker for Source {Source}: the account cannot delete on the server", source.Name);
                continue;
            }

            using var body = new MemoryStream(System.Text.Encoding.UTF8.GetBytes($"{{\"runId\":\"{run.RunId}\"}}\n"));
            if ((await session.UploadAsync(body, marker, ct)).IsOk) placed.Add(marker);
        }
        return placed;
    }

    private async Task WorkerAsync(ChannelReader<object> reader, RunState run, ConcurrentQueue<string> connectFailure, CancellationToken ct)
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
            if (item is ArchiveWork archive) await ProcessArchiveAsync(session, archive, run, ct);
            else await ProcessAsync(session, (FileWork)item, run, ct);
        }
    }

    private async Task ProcessAsync(IRemoteSession session, FileWork item, RunState run, CancellationToken ct)
    {
        var store = run.Store;
        var key = item.Key(_settings.Destination);
        var mtime = item.File.ChangeToken;
        if (IsUnchanged(item, out var prior))
        {
            var remoteLevel = _settings.Verification.Remote;
            var remoteOk = true;
            if (remoteLevel != VerificationLevel.Off)
            {
                run.Set(item, FileOutcome.Verifying, null);
                var check = await VerifyAsync(session, remoteLevel, Join(item.RemotePath, item.File.RelativePath), item.File.Size, prior.Sha256!, ct);
                remoteOk = check.Ok;
                if (check.Ok) run.CountVerified();
                else _logger.LogInformation("{Source}/{Path}: unchanged, but {Reason}; uploading it again", item.Source.Name, item.File.RelativePath, check.Detail);
            }
            if (remoteOk)
            {
                run.Skip(item, prior.Sha256!, UnchangedReason);
                store?.RecordSkipped(run.RunId, key, _time.GetUtcNow());
                return;
            }
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
                if (attemptResult.Verified) run.CountVerified();
                run.Succeed(item, attemptResult.Sha256, _time.GetElapsedTime(started), IsDirect);
                store?.RecordSucceeded(run.RunId, key, item.File.Size, mtime, attemptResult.Sha256, _time.GetUtcNow(), _time.GetElapsedTime(started), IsDirect);
                return;
            }

            failure = attemptResult.Reason ?? "unknown";
            _logger.LogWarning("Upload of {Source}/{Path} failed (attempt {Attempt}/{Max}): {Reason}",
                item.Source.Name, item.File.RelativePath, attempt, max, failure);
            if (attemptResult.Permanent) break;
            if (attempt < max) await Task.Delay(BackoffDelay(attempt), _time, ct);
        }

        if (failure.StartsWith(VerificationFailedReason, StringComparison.Ordinal)) run.CountVerificationFailure();
        run.Fail(item, failure, _time.GetElapsedTime(started));
        store?.RecordFailed(run.RunId, key, item.File.Size, mtime, failure, _time.GetUtcNow(), _time.GetElapsedTime(started));
    }

    private const string UnchangedReason = "unchanged";

    private bool IsDirect => _settings.UploadStrategy == UploadStrategy.Direct;

    /// <summary>Where the bytes of <paramref name="finalPath"/> are written first: <c>name.part</c>, or the final name itself for Direct.</summary>
    private string UploadTarget(string finalPath) => IsDirect ? finalPath : finalPath + ".part";

    /// <summary>The size and mtime fast path: the Upload State has this file Succeeded with the same size and mtime.</summary>
    private static bool IsUnchanged(FileWork item, out PriorFile prior)
    {
        prior = item.Prior!;
        return item.Prior is { Status: "Succeeded", Sha256: not null } known
            && known.Size == item.File.Size && known.MtimeTicks == item.File.ChangeToken;
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
        // The object the bytes are written to: a .part that is renamed afterwards, or the final name itself (Direct).
        var partPath = UploadTarget(finalPath);
        try
        {
            var ensure = await session.EnsureDirectoryAsync(ParentOf(finalPath), ct);
            if (!ensure.IsOk) return UploadAttempt.From(ensure);

            if (run.Store is { } store)
                await store.MarkUploadingAsync(item.Key(_settings.Destination), item.File.Size, item.File.ChangeToken, partPath);

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

            // Verification looks at the .part, so a bad file never appears under its final name.
            var level = _settings.Verification.AfterUpload;
            if (level != VerificationLevel.Off)
            {
                run.Set(item, FileOutcome.Verifying, null);
                var check = await VerifyAsync(session, level, partPath, bytesRead, sha256, ct);
                if (!check.Ok)
                {
                    await session.DeleteAsync(partPath, ct);
                    return new UploadAttempt(null, $"{VerificationFailedReason}: {check.Detail}", false);
                }
            }

            if (!IsDirect)
            {
                var rename = await session.RenameAsync(partPath, finalPath, overwrite: true, ct);
                if (!rename.IsOk) return UploadAttempt.From(rename);
            }
            return new UploadAttempt(sha256, null, false, Verified: level != VerificationLevel.Off);
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
        if (now.ChangeToken != listed.ChangeToken)
            return listed.ETag is null
                ? $"modified at {now.Modified:O}, listed {listed.Modified:O}"
                : $"ETag is now {now.ETag}, listed {listed.ETag}";
        return null;
    }

    private async Task<RemoteResult> UploadManifestAsync(IRemoteSession session, ISource source, RunState run, RunOptions options, CancellationToken ct)
    {
        var remotePath = RemotePathOf(source);

        var ensure = await session.EnsureDirectoryAsync(remotePath, ct);
        if (!ensure.IsOk) return ensure;

        var (nodes, failures) = await ManifestContentAsync(source, remotePath, run);
        var deferred = run.SourceEntries(source.Name)
            .Where(e => !e.Carried && e.Outcome == FileOutcome.Skipped && e.Reason == TooRecentReason)
            .Select(e => new ManifestFailure(e.Path, e.Reason!)).ToList();
        var complete = failures.Count == 0 && deferred.Count == 0;
        var completedAt = _time.GetUtcNow();
        var store = run.Store;

        async Task<RemoteResult> UploadAsync(string jsonName, string flatName, IReadOnlyList<string> supersedes)
        {
            var header = new ManifestHeader(source.Name, complete, run.RunId, run.StartedAt, completedAt,
                ModeOf(options), _settings.ToolVersion, _settings.MachineName) { Supersedes = supersedes };
            await using var json = TemporaryFile();
            ManifestWriter.Write(json, header, failures, deferred, nodes);
            json.Position = 0;
            var (result, jsonSha256) = await UploadFinalAsync(session, json, Join(remotePath, jsonName), ct);
            if (!result.IsOk || !_settings.WriteFlatManifest) return result;

            await using var flat = TemporaryFile();
            ManifestWriter.WriteFlat(flat, nodes(), jsonName, jsonSha256!);
            flat.Position = 0;
            return (await UploadFinalAsync(session, flat, Join(remotePath, flatName), ct)).Result;
        }

        async Task Remember(string jsonName)
        {
            if (store is not null) await store.RecordManifestAsync(_settings.Destination, remotePath, source.Name, jsonName, run.RunId, _time.GetUtcNow());
        }

        // The stable names come first; a server that refuses to replace them is remembered per Destination, and from then on
        // every Run uploads Manifest files of its own, which are never overwritten.
        var earlier = store?.LoadManifestNames(_settings.Destination, remotePath, source.Name) ?? [];
        var refused = store?.IsManifestOverwriteRefused(_settings.Destination) == true;
        if (!refused)
        {
            var stable = await UploadAsync(_settings.ManifestName, _settings.FlatManifestName, earlier.Where(n => n != _settings.ManifestName).ToList());
            if (stable.IsOk)
            {
                await Remember(_settings.ManifestName);
                return stable;
            }
            if (stable.Kind != RemoteResultKind.Denied) return stable;
            _logger.LogInformation("The server refused to replace {Manifest} ({Reason}); this Destination now gets a Manifest per Run", _settings.ManifestName, stable.Reason);
            if (store is not null) await store.RememberManifestOverwriteRefusedAsync(_settings.Destination);
            if (!earlier.Contains(_settings.ManifestName)) earlier = [.. earlier, _settings.ManifestName];
        }

        var stampedJson = RunStamped(_settings.ManifestName, run.RunId);
        var uploaded = await UploadAsync(stampedJson, RunStamped(_settings.FlatManifestName, run.RunId), earlier);
        if (uploaded.IsOk) await Remember(stampedJson);
        return uploaded;
    }

    /// <summary><c>manifest.json</c> becomes <c>manifest.&lt;runId&gt;.json</c>.</summary>
    internal static string RunStamped(string name, Guid runId)
    {
        var extension = Path.GetExtension(name);
        return $"{name[..^extension.Length]}.{runId}{extension}";
    }

    /// <summary>
    /// What the Manifest of the Source lists: everything the Upload State knows to be on the server (cumulative over Runs),
    /// or this Run's own results when there is no Upload State.
    /// </summary>
    private async Task<(Func<IEnumerable<ManifestNode>> Nodes, List<ManifestFailure> Failures)> ManifestContentAsync(ISource source, string remotePath, RunState run)
    {
        if (run.Store is { } store)
        {
            await store.FlushAsync();
            return (() => store.EnumerateDelivered(_settings.Destination, remotePath, source.Name),
                store.LoadFailures(_settings.Destination, remotePath, source.Name));
        }

        var entries = run.SourceEntries(source.Name);
        var byPath = entries.ToDictionary(e => e.Path, StringComparer.Ordinal);
        var archives = run.SourceArchives(source.Name);
        IEnumerable<ManifestNode> Nodes() =>
            entries.Where(e => e.ArchivePath is null && e.Sha256 is not null && e.Outcome is FileOutcome.Succeeded or FileOutcome.Skipped)
                .Select(e => (ManifestNode)new ManifestFile(e.Path, e.Size, e.Sha256!) { DirectUpload = e.DirectUpload })
                .Concat(archives.Select(a => (ManifestNode)new ManifestArchive(a.Path, a.Size, a.Sha256!,
                    a.Members.Select(m => byPath[m]).OrderBy(m => m.Path, StringComparer.Ordinal)
                        .Select(m => new ManifestArchiveMember(m.Path, m.Size, m.Sha256!, m.Modified)).ToList()) { DirectUpload = a.DirectUpload }))
                .OrderBy(n => n.Path, StringComparer.Ordinal);
        return (Nodes, entries.Where(e => e.Outcome == FileOutcome.Failed).Select(e => new ManifestFailure(e.Path, e.Reason ?? "Failed")).ToList());
    }

    private static FileStream TemporaryFile() =>
        new(Path.Combine(Path.GetTempPath(), "mires-manifest-" + Guid.NewGuid().ToString("N")), FileMode.CreateNew, FileAccess.ReadWrite,
            FileShare.None, 81920, FileOptions.DeleteOnClose);

    /// <summary>
    /// Uploads the stream to its final name the way <c>UploadStrategy</c> says: through <c>name.part</c> and a rename, or straight
    /// to the name. Returns the SHA-256 of what was sent.
    /// </summary>
    private async Task<(RemoteResult Result, string? Sha256)> UploadFinalAsync(IRemoteSession session, Stream content, string finalPath, CancellationToken ct)
    {
        var target = UploadTarget(finalPath);
        string sha256;
        await using (var hashing = new HashingReadStream(content))
        {
            var upload = await session.UploadAsync(hashing, target, ct);
            if (!upload.IsOk) return (upload, null);
            sha256 = hashing.FinishHash();
        }
        if (IsDirect) return (RemoteResult.Ok, sha256);
        var rename = await session.RenameAsync(target, finalPath, overwrite: true, ct);
        return (rename, rename.IsOk ? sha256 : null);
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
            alwaysNames: UploadStateFileNames());
    }

    /// <summary>
    /// Root-level names the Run itself writes into a Source's Remote Path. A Source file with one of them (not ignored by a rule)
    /// would be overwritten by the Manifest, so the Run refuses to start (exit 2). Compared without regard to case.
    /// </summary>
    private HashSet<string> ReservedManifestNames()
    {
        var json = _settings.ManifestName;
        var flat = _settings.FlatManifestName;
        return new HashSet<string>(
        [
            json, json + ".part", json + _settings.InProgressSuffix, json + _settings.InProgressSuffix + ".probe",
            flat, flat + ".part",
        ], StringComparer.OrdinalIgnoreCase);
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

    private sealed record UploadAttempt(string? Sha256, string? Reason, bool Permanent, bool Verified = false)
    {
        public static UploadAttempt From(RemoteResult failed) =>
            failed.Kind == RemoteResultKind.Denied
                ? new UploadAttempt(null, "RemoteDenied: " + failed.Reason, true)
                : new UploadAttempt(null, failed.Reason, false);
    }

    /// <summary>Mutable state of one Run: outcome per file, hashes and failures for the Manifest.</summary>
    internal sealed partial class RunState(Guid runId, DateTimeOffset startedAt, IProgress<RunEvent> progress, ILogger logger)
    {
        private readonly object _gate = new();
        private readonly Dictionary<(string Source, string Path), FileEntry> _entries = new();

        public Guid RunId { get; } = runId;
        public DateTimeOffset StartedAt { get; } = startedAt;
        public UploadStateStore? Store { get; set; }
        /// <summary>The account has Write-only Access: the Run trusts the Upload State instead of the server.</summary>
        public bool WriteOnly { get; set; }
        public string WriteOnlyReason { get; set; } = "";

        private int _verified;
        private int _verificationFailures;
        /// <summary>Files and Archives whose Verification passed.</summary>
        public int Verified => Volatile.Read(ref _verified);
        /// <summary>Files and Archives that ended Failed because Verification kept failing.</summary>
        public int VerificationFailures => Volatile.Read(ref _verificationFailures);
        internal void CountVerified() => Interlocked.Increment(ref _verified);
        internal void CountVerificationFailure() => Interlocked.Increment(ref _verificationFailures);

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

        internal void Succeed(FileWork item, string sha256, TimeSpan duration, bool directUpload = false) =>
            Update(item, e => { e.Outcome = FileOutcome.Succeeded; e.Reason = null; e.Sha256 = sha256; e.Bytes = e.Size; e.DurationMs = (long)duration.TotalMilliseconds; e.DirectUpload = directUpload; });

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
                    _entries[key] = entry = new FileEntry(item.Source.Name, item.File.RelativePath, item.File.Size) { Modified = item.File.Modified };
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

    internal sealed partial class FileEntry(string source, string path, long size)
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
        public bool DirectUpload { get; set; }

        public FileEntry Clone() => new(Source, Path, Size) { DirectUpload = DirectUpload, Outcome = Outcome, Reason = Reason, Sha256 = Sha256, Bytes = Bytes, DurationMs = DurationMs, Carried = Carried, Modified = Modified, ArchivePath = ArchivePath, EntryName = EntryName };
    }
}

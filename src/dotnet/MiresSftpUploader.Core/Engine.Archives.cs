using Microsoft.Extensions.Logging;

namespace MiresSftpUploader.Core;

// Archives: planning, building in the Staging Area, skip decisions and upload.
public sealed partial class Engine
{
    internal const string ArchiveNameCollisionReason = "ArchiveNameCollision";
    internal const string InsufficientStagingSpaceReason = "InsufficientStagingSpace";

    internal sealed record ArchiveWork(ISource Source, string RemotePath, PlannedArchive Plan, PriorArchive? Prior, bool Delivered = false)
    {
        public FileKey Key(string destination) => new(destination, RemotePath, Source.Name, Plan.RelativePath);
    }

    /// <summary>The Source's own Archive Rules are tried before the global ones; the first match wins.</summary>
    private IReadOnlyList<ArchiveRuleConfig> ArchiveRulesOf(ISource source)
    {
        var own = _settings.SourceConfigs
            .FirstOrDefault(c => string.Equals(c.Name, source.Name, StringComparison.OrdinalIgnoreCase))?.ArchiveRules ?? [];
        return [.. own, .. _settings.Archive.Rules];
    }

    /// <summary>Scans a Source and returns the Archives its rules call for, without recording anything.</summary>
    private async Task<IReadOnlyList<PlannedArchive>> PlanArchivesAsync(ISource source, string remotePath, RunState run, CancellationToken ct)
    {
        var rules = IgnoreRulesOf(source);
        var candidates = new List<(FileWork Item, bool TooRecent)>();
        await foreach (var file in source.ListAsync(ct))
            if (rules.Reason(file.RelativePath) is null)
                candidates.Add((new FileWork(source, remotePath, file), IsTooRecent(source, file)));
        return ArchivePlanner.Plan(ArchiveRulesOf(source), candidates, source.Name, run.StartedAt).Archives;
    }

    /// <summary>
    /// Decides what a planned Archive means for this Run and records the outcomes that need no work: a name collision
    /// fails its members, a Too Recent member defers the whole Archive. In a Dry Run it also reports the plan.
    /// Returns true when the Archive must be processed by a worker.
    /// </summary>
    private bool PlanArchive(ArchiveWork work, RunState run, bool dryRun)
    {
        var plan = work.Plan;
        var sourceName = work.Source.Name;
        var skipStatus = ArchiveStatus(work);

        if (plan.TotalSize > _settings.Archive.WarnAboveBytes)
            run.Warn($"Archive {plan.RelativePath} of Source {sourceName} is {plan.TotalSize} bytes, above Archive:WarnAboveBytes.");

        if (plan.NameCollision)
        {
            run.AddArchive(sourceName, plan, FileOutcome.Failed,
                $"{ArchiveNameCollisionReason}: {plan.RelativePath} is also the name of another file or Archive");
            if (dryRun) run.Report(new ArchivePlanned(sourceName, plan.RelativePath, plan.RuleName, plan.Members.Count, plan.TotalSize, 0, ArchiveNameCollisionReason));
            return false;
        }
        if (plan.DeferredTooRecent)
        {
            run.AddArchive(sourceName, plan, FileOutcome.Skipped, TooRecentReason);
            if (dryRun) run.Report(new ArchivePlanned(sourceName, plan.RelativePath, plan.RuleName, plan.Members.Count, plan.TotalSize, 0, TooRecentReason));
            return false;
        }

        if (!dryRun)
        {
            run.AddArchive(sourceName, plan, FileOutcome.Pending, null);
            return true;
        }

        if (skipStatus == ArchiveStatuses.WouldSkip)
        {
            run.AddArchive(sourceName, plan, FileOutcome.Skipped, UnchangedReason);
            run.CompleteArchive(sourceName, plan.RelativePath, work.Prior!.File.Size, work.Prior.File.Sha256!, work.Prior.Members);
        }
        else
        {
            run.AddArchive(sourceName, plan, FileOutcome.Pending, $"Would be packed into {plan.RelativePath} (rule {plan.RuleName})");
        }
        var estimate = skipStatus == ArchiveStatuses.WouldSkip ? 0 : plan.TotalSize;
        if (estimate > 0 && StagingShortfall(estimate) is { } shortfall) run.Warn(shortfall);
        run.Report(new ArchivePlanned(sourceName, plan.RelativePath, plan.RuleName, plan.Members.Count, plan.TotalSize, estimate, skipStatus));
        return false;
    }

    /// <summary>
    /// The fast path: the Upload State has this Archive Succeeded with exactly these members at the same size and mtime,
    /// so no member needs reading. "NeedsHashing" means the same members but changed size or mtime.
    /// </summary>
    private static string ArchiveStatus(ArchiveWork work)
    {
        if (work.Prior is not { File.Status: "Succeeded", File.Sha256: not null } prior) return ArchiveStatuses.WouldBuild;
        var members = work.Plan.Members;
        if (prior.Members.Count != members.Count || members.Any(m => !prior.Members.ContainsKey(m.Item.File.RelativePath)))
            return ArchiveStatuses.WouldBuild;
        var unchanged = members.All(m =>
            prior.Members[m.Item.File.RelativePath] is var p && p.Size == m.Item.File.Size && p.MtimeTicks == m.Item.File.ChangeToken);
        return unchanged ? ArchiveStatuses.WouldSkip : ArchiveStatuses.NeedsHashing;
    }

    private async Task ProcessArchiveAsync(IRemoteSession session, ArchiveWork work, RunState run, CancellationToken ct)
    {
        var plan = work.Plan;
        var store = run.Store;
        var key = work.Key(_settings.Destination);
        var started = _time.GetTimestamp();

        if (ArchiveStatus(work) == ArchiveStatuses.WouldSkip)
        {
            var prior = work.Prior!;
            foreach (var m in plan.Members) run.Skip(m.Item, prior.Members[m.Item.File.RelativePath].Sha256, UnchangedReason);
            run.CompleteArchive(work.Source.Name, plan.RelativePath, prior.File.Size, prior.File.Sha256!, prior.Members);
            store?.RecordSkipped(run.RunId, key, _time.GetUtcNow());
            return;
        }

        foreach (var m in plan.Members) run.Set(m.Item, FileOutcome.Hashing, null);

        if (StagingShortfall(plan.TotalSize) is { } shortfall)
        {
            FailArchive(work, run, shortfall, started);
            return;
        }

        // At most two staged Archives exist at once: one building while one uploads.
        await run.StagedGate.WaitAsync(ct);
        var staged = Path.Combine(StagingDirectory(run), $"{Guid.NewGuid():N}.zip");
        try
        {
            ArchiveBuild build;
            await run.BuildGate.WaitAsync(ct);
            try
            {
                build = await ArchiveBuilder.BuildAsync(staged,
                    work.Source, plan.Members.Select(m => new ArchiveMemberSpec(m.Item.File, m.EntryName)).ToList(), ct);
            }
            finally
            {
                run.BuildGate.Release();
            }
            if (build.Failure is not null)
            {
                FailArchive(work, run, build.Failure, started);
                return;
            }

            var members = plan.Members
                .Select(m => new ArchiveMemberRecord(m.Item.File.RelativePath, m.Item.File.Size, m.Item.File.ChangeToken, build.MemberHashes[m.Item.File.RelativePath], m.Item.File.Modified.UtcTicks))
                .ToList();
            var memberHashes = members.ToDictionary(m => m.Path, m => new PriorMember(m.Size, m.MtimeTicks, m.Sha256), StringComparer.Ordinal);

            var remoteArchiveOk = true;
            if (work.Prior is { File.Status: "Succeeded" } unchangedPrior && SameMembers(unchangedPrior.Members, memberHashes)
                && _settings.Verification.Remote != VerificationLevel.Off)
            {
                foreach (var m in plan.Members) run.Set(m.Item, FileOutcome.Verifying, null);
                var check = await VerifyAsync(session, _settings.Verification.Remote, Join(work.RemotePath, plan.RelativePath), build.ZipSize, build.ZipSha256!, ct);
                remoteArchiveOk = check.Ok;
                if (check.Ok) run.CountVerified();
                else _logger.LogInformation("{Source}/{Path}: Archive unchanged, but {Reason}; uploading it again", work.Source.Name, plan.RelativePath, check.Detail);
            }

            if (remoteArchiveOk && work.Prior is { File.Status: "Succeeded" } prior && SameMembers(prior.Members, memberHashes))
            {
                foreach (var m in plan.Members) run.Skip(m.Item, memberHashes[m.Item.File.RelativePath].Sha256, UnchangedReason);
                run.CompleteArchive(work.Source.Name, plan.RelativePath, build.ZipSize, build.ZipSha256!, memberHashes);
                store?.RecordArchiveSucceeded(run.RunId, key, build.ZipSize, build.ZipSha256!, members, uploaded: false, _time.GetUtcNow(), TimeSpan.Zero);
                return;
            }

            var finalPath = Join(work.RemotePath, plan.RelativePath);
            var (uploaded, failure) = await UploadWithRetriesAsync($"Archive {work.Source.Name}/{plan.RelativePath}", attempt =>
            {
                foreach (var m in plan.Members) run.Set(m.Item, FileOutcome.Uploading, null);
                return TryUploadStagedAsync(session, run, attempt, store, staged, finalPath, (work.Source.Name, plan.RelativePath), key, build.ZipSize, build.ZipSha256!, work.Delivered,
                    () => { foreach (var m in plan.Members) run.Set(m.Item, FileOutcome.Verifying, null); }, ct);
            }, ct);
            if (uploaded is not null)
            {
                if (uploaded.Verified) run.CountVerified();
                foreach (var m in plan.Members) run.Succeed(m.Item, memberHashes[m.Item.File.RelativePath].Sha256, _time.GetElapsedTime(started));
                run.CompleteArchive(work.Source.Name, plan.RelativePath, build.ZipSize, build.ZipSha256!, memberHashes, IsDirect);
                store?.RecordArchiveSucceeded(run.RunId, key, build.ZipSize, build.ZipSha256!, members, uploaded: true, _time.GetUtcNow(), _time.GetElapsedTime(started), IsDirect, uploaded.UploadTime);
                return;
            }
            if (failure.StartsWith(VerificationFailedReason, StringComparison.Ordinal)) run.CountVerificationFailure();
            FailArchive(work, run, failure, started);
        }
        finally
        {
            TryDelete(staged);
            run.StagedGate.Release();
        }
    }

    private static bool SameMembers(IReadOnlyDictionary<string, PriorMember> before, IReadOnlyDictionary<string, PriorMember> now) =>
        before.Count == now.Count && now.All(kv => before.TryGetValue(kv.Key, out var p) && p.Sha256 == kv.Value.Sha256);

    private async Task<UploadAttempt> TryUploadStagedAsync(
        IRemoteSession session, RunState run, int attempt, UploadStateStore? store, string stagedPath, string finalPath, (string Source, string Path) label, FileKey key, long zipSize, string zipSha256, bool delivered, Action markVerifying, CancellationToken ct)
    {
        var partPath = UploadTarget(finalPath, run, attempt);
        try
        {
            var ensure = await session.EnsureDirectoryAsync(ParentOf(finalPath), ct);
            if (!ensure.IsOk) return UploadAttempt.From(ensure);
            if (store is not null) await store.MarkUploadingAsync(key, zipSize, 0, partPath);

            TimeSpan uploadTime;
            await using (var staged = new FileStream(stagedPath, FileMode.Open, FileAccess.Read, FileShare.Read, 81920, FileOptions.Asynchronous | FileOptions.SequentialScan))
            {
                var uploadStarted = _time.GetTimestamp();
                var upload = await session.UploadAsync(staged, partPath, ct, metered);
                uploadTime = _time.GetElapsedTime(uploadStarted);
                if (!upload.IsOk) return UploadAttempt.From(upload);
            }
            var level = _settings.Verification.AfterUpload;
            if (level != VerificationLevel.Off)
            {
                markVerifying();
                var check = await VerifyAsync(session, level, partPath, zipSize, zipSha256, ct);
                if (!check.Ok)
                {
                    await DiscardBadUploadAsync(session, partPath, delivered, ct);
                    return new UploadAttempt(null, $"{VerificationFailedReason}: {check.Detail}", false);
                }
            }
            if (!IsDirect)
            {
                var rename = await session.RenameAsync(partPath, finalPath, overwrite: true, ct);
                if (!rename.IsOk) return UploadAttempt.From(rename);
            }
            return new UploadAttempt("uploaded", null, false, Verified: level != VerificationLevel.Off, UploadTime: uploadTime);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            return new UploadAttempt(null, ex.Message, false);
        }
    }

    /// <summary>All or nothing: every member is Failed with the reason, which names the culprit.</summary>
    private void FailArchive(ArchiveWork work, RunState run, string reason, long started)
    {
        _logger.LogWarning("Archive {Source}/{Path} failed: {Reason}", work.Source.Name, work.Plan.RelativePath, reason);
        foreach (var m in work.Plan.Members) run.Fail(m.Item, reason, _time.GetElapsedTime(started));
        run.Store?.RecordFailed(run.RunId, work.Key(_settings.Destination), 0, 0, Redact(reason), _time.GetUtcNow(), _time.GetElapsedTime(started));
    }

    // ---- Staging Area ----

    private string StagingRoot =>
        _settings.Archive.StagingPath is { Length: > 0 } configured ? configured
        : _settings.State.Path is { Length: > 0 } database
            ? Path.Combine(Path.GetDirectoryName(Path.GetFullPath(database))!, "staging")
            : Path.Combine(Path.GetTempPath(), "mires-sftp-uploader", "staging");

    private string StagingDirectory(RunState run) => Path.Combine(StagingRoot, run.RunId.ToString());

    /// <summary>Null when the Staging Area has room for <paramref name="needed"/> bytes plus the configured reserve.</summary>
    private string? StagingShortfall(long needed)
    {
        var reserve = _settings.Archive.MinFreeSpaceBytes;
        var required = needed > long.MaxValue - reserve ? long.MaxValue : needed + reserve;
        var available = AvailableFreeSpace(StagingRoot);
        return available is { } free && free < required
            ? $"{InsufficientStagingSpaceReason}: {free} bytes free in {StagingRoot}, {required} needed"
            : null;
    }

    private static long? AvailableFreeSpace(string path)
    {
        try
        {
            var directory = Path.GetFullPath(path);
            while (!Directory.Exists(directory) && Path.GetDirectoryName(directory) is { } parent) directory = parent;
            return new DriveInfo(OperatingSystem.IsWindows() ? Path.GetPathRoot(directory)! : directory).AvailableFreeSpace;
        }
        catch (Exception ex) when (ex is ArgumentException or IOException or UnauthorizedAccessException)
        {
            return null;
        }
    }

    /// <summary>Removes this Run's Staging Area at the end of the Run, however it ended.</summary>
    private void DeleteStagingArea(RunState run) => TryDeleteDirectory(StagingDirectory(run));

    /// <summary>
    /// A Run holding the lock is the only live Run, so every other folder in the staging root belongs to a Run that died.
    /// </summary>
    private void RemoveStaleStagingAreas(RunState run)
    {
        if (!Directory.Exists(StagingRoot)) return;
        foreach (var directory in Directory.EnumerateDirectories(StagingRoot))
        {
            if (Path.GetFileName(directory) == run.RunId.ToString()) continue;
            if (!TryDeleteDirectory(directory))
                _logger.LogWarning("Could not remove the leftover Staging Area {Path}", directory);
        }
    }

    private static bool TryDeleteDirectory(string path)
    {
        try
        {
            if (Directory.Exists(path)) Directory.Delete(path, recursive: true);
            return true;
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            return false;
        }
    }

    private static void TryDelete(string path)
    {
        try { File.Delete(path); } catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { }
    }

    // ---- Run state for Archives ----

    internal sealed partial class RunState
    {
        private readonly Dictionary<(string Source, string Path), ArchiveEntry> _archives = new();

        public SemaphoreSlim BuildGate { get; set; } = new(1);
        public SemaphoreSlim StagedGate { get; } = new(2);

        /// <summary>Registers an Archive and gives each of its members the initial outcome.</summary>
        internal void AddArchive(string source, PlannedArchive plan, FileOutcome initial, string? reason)
        {
            lock (_gate)
                _archives[(source, plan.RelativePath)] = new ArchiveEntry(plan.RelativePath, plan.RuleName,
                    plan.Members.Select(m => m.Item.File.RelativePath).ToList());
            foreach (var m in plan.Members)
                Update(m.Item, e =>
                {
                    e.Outcome = initial;
                    e.Reason = reason;
                    e.ArchivePath = plan.RelativePath;
                    e.EntryName = m.EntryName;
                });
        }

        internal void CompleteArchive(string source, string path, long size, string sha256, IReadOnlyDictionary<string, PriorMember> members, bool directUpload = false)
        {
            lock (_gate)
            {
                var entry = _archives[(source, path)];
                entry.Size = size;
                entry.Sha256 = sha256;
                entry.DirectUpload = directUpload;
                foreach (var (memberPath, member) in members)
                    if (_entries.TryGetValue((source, memberPath), out var e)) e.Sha256 ??= member.Sha256;
            }
        }

        /// <summary>An Archive delivered by an earlier Run: listed in the Manifest with its members, not an outcome of this Run.</summary>
        internal void CarryArchive(string source, string path, long size, string sha256, IReadOnlyDictionary<string, PriorMember> members)
        {
            var directory = path.Contains('/') ? path[..path.LastIndexOf('/')] + "/" : "";
            lock (_gate)
            {
                _archives[(source, path)] = new ArchiveEntry(path, "", members.Keys.ToList()) { Size = size, Sha256 = sha256 };
                foreach (var (memberPath, member) in members)
                    _entries[(source, memberPath)] = new FileEntry(source, memberPath, member.Size)
                    {
                        Outcome = FileOutcome.Skipped, Reason = "delivered earlier", Sha256 = member.Sha256, Carried = true,
                        Modified = new DateTimeOffset(member.MtimeTicks, TimeSpan.Zero), ArchivePath = path,
                        EntryName = directory.Length > 0 && memberPath.StartsWith(directory, StringComparison.Ordinal) ? memberPath[directory.Length..] : memberPath,
                    };
            }
        }

        public IReadOnlyList<ArchiveEntry> SourceArchives(string source)
        {
            lock (_gate)
                return _archives.Where(kv => kv.Key.Source == source && kv.Value.Sha256 is not null)
                    .OrderBy(kv => kv.Key.Path, StringComparer.Ordinal)
                    .Select(kv => kv.Value.Clone())
                    .ToList();
        }
    }

    internal sealed class ArchiveEntry(string path, string rule, IReadOnlyList<string> members)
    {
        public string Path { get; } = path;
        public string Rule { get; } = rule;
        public IReadOnlyList<string> Members { get; } = members;
        public long Size { get; set; }
        public string? Sha256 { get; set; }
        public bool DirectUpload { get; set; }

        public ArchiveEntry Clone() => new(Path, Rule, Members) { Size = Size, Sha256 = Sha256, DirectUpload = DirectUpload };
    }

    internal sealed partial class FileEntry
    {
        public DateTimeOffset Modified { get; set; }
        /// <summary>Source-relative path of the Archive this file went into, or null for an ordinary file.</summary>
        public string? ArchivePath { get; set; }
        /// <summary>The member's name inside its Archive.</summary>
        public string? EntryName { get; set; }
    }

    private static class ArchiveStatuses
    {
        public const string WouldSkip = "WouldSkip";
        public const string WouldBuild = "WouldBuild";
        public const string NeedsHashing = "NeedsHashing";
    }
}

namespace MiresSftpUploader.Core;

public abstract record RunEvent;

public sealed record RunStarted(Guid RunId, DateTimeOffset StartedAt) : RunEvent;

public sealed record FileOutcomeChanged(string Source, string RelativePath, FileOutcome Outcome, string? Reason) : RunEvent;

/// <summary>
/// A Dry Run's plan for one Archive. <see cref="Status"/> is WouldBuild, WouldSkip, NeedsHashing (same members, changed size or mtime),
/// TooRecent (deferred whole) or ArchiveNameCollision. <see cref="StagingEstimate"/> is the Staging Area space a build needs.
/// </summary>
public sealed record ArchivePlanned(
    string Source, string Name, string Rule, int MemberCount, long TotalSize, long StagingEstimate, string Status) : RunEvent;

/// <summary>The Data Directory access check, reported at each Run start (also when it failed).</summary>
public sealed record DataDirectoryChecked(DataDirectoryAccess Access) : RunEvent;

/// <summary>A file left its Source through a Post-upload Move.</summary>
public sealed record FileMoved(string Source, string RelativePath) : RunEvent;

public sealed record RunWarning(string Message) : RunEvent;

public sealed record RunFinished(RunResult Result) : RunEvent;

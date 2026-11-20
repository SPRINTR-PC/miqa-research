namespace MiresSftpUploader.Core;

public abstract record RunEvent;

public sealed record RunStarted(Guid RunId, DateTimeOffset StartedAt) : RunEvent;

public sealed record FileOutcomeChanged(string Source, string RelativePath, FileOutcome Outcome, string? Reason,
    long? BytesSent = null, TimeSpan? UploadTime = null) : RunEvent;

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

/// <summary>One file (or Archive) that is uploading now: the bytes the server acknowledged so far and its Upload Speed in bytes per second (null until 2 samples exist).</summary>
public sealed record UploadingFile(string Source, string RelativePath, long BytesSent, long Total, double? UploadSpeed, bool IsArchive = false)
{
    public TransferKey Key => new(Source, RelativePath, IsArchive);
}

/// <summary>Identifies one file or Archive in a Run. An Archive is keyed apart from a file, so an Archive path equal to a file path cannot collide with it.</summary>
public readonly record struct TransferKey(string Source, string Path, bool IsArchive = false);

/// <summary>
/// A snapshot of every file uploading now, about 4 times a second, with the total Upload Speed over them (bytes per second; null
/// when no file has one yet). A last snapshot with no files clears the total. A Scan or Dry Run emits none.
/// </summary>
public sealed record UploadProgress(IReadOnlyList<UploadingFile> Files, double? TotalUploadSpeed) : RunEvent;

public sealed record RunWarning(string Message) : RunEvent;

public sealed record RunFinished(RunResult Result) : RunEvent;

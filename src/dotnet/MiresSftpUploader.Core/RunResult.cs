namespace MiresSftpUploader.Core;

public static class ExitCodes
{
    public const int Ok = 0;
    public const int SomeFilesFailed = 1;
    public const int ConfigurationError = 2;
    public const int ConnectFailed = 3;
    public const int LockHeld = 4;
    public const int Cancelled = 130;
}

/// <summary>The result of a Run: counts per File Outcome and the exit code.</summary>
public sealed record RunResult(
    Guid RunId,
    IReadOnlyDictionary<FileOutcome, int> Counts,
    int ExitCode,
    string? Reason,
    int Verified = 0,
    int VerificationFailures = 0)
{
    /// <summary>Where the Report of this Run was written; null when none was.</summary>
    public string? ReportPath { get; init; }

    /// <summary>Files moved out of their Source by a Post-upload Move.</summary>
    public int MovedAway { get; init; }

    /// <summary>Moves that did not happen (target exists, copy failed, file changed since): warnings, not upload failures.</summary>
    public int MoveFailures { get; init; }

    public int Count(FileOutcome outcome) => Counts.TryGetValue(outcome, out var n) ? n : 0;
}

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
    string? Reason)
{
    /// <summary>Where the Report of this Run was written; null when none was.</summary>
    public string? ReportPath { get; init; }

    public int Count(FileOutcome outcome) => Counts.TryGetValue(outcome, out var n) ? n : 0;
}

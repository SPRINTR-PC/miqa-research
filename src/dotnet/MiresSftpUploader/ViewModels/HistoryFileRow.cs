using MiresSftpUploader.Core;

namespace MiresSftpUploader.ViewModels;

/// <summary>One recorded file outcome of a Run in the Run History. The outcome is the stored name, so outcomes the live list does not know (MovedAway) show as they are.</summary>
public sealed class HistoryFileRow(RunFileOutcome file)
{
    public string Source { get; } = file.Source;
    public string Path { get; } = file.RelativePath;
    public string Outcome { get; } = file.Outcome;
    public string? Reason { get; } = file.Reason;
    public long Bytes { get; } = file.Bytes;

    public string OutcomeText => Outcome == "MovedAway" ? "Moved away" : Outcome;
    public string ReasonText => Reason switch { null or "" => "", "TooRecent" => "Too Recent", var r => r };
    public bool IsFailed => Outcome == "Failed";
    public bool IsSucceeded => Outcome == "Succeeded";
    public bool IsMuted => Outcome is "Pending" or "Skipped" or "Ignored" or "MovedAway";
    public bool IsActive => Outcome is "Hashing" or "Uploading" or "Verifying";
}

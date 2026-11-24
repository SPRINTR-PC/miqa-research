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
    public long? UploadMs { get; } = file.UploadMs;

    public string OutcomeText => Outcome == "MovedAway" ? "Moved away" : Outcome;
    public string ReasonText => Reason switch { null or "" => "", "TooRecent" => "Too Recent", var r => r };
    public bool IsFailed => Outcome == "Failed";
    public bool IsSucceeded => Outcome == "Succeeded";
    public bool IsMuted => Outcome is "Pending" or "Skipped" or "Ignored" or "MovedAway";
    public bool IsActive => Outcome is "Hashing" or "Uploading" or "Verifying";

    private bool HasTransfer => IsSucceeded && UploadMs is not null;

    /// <summary>"12.4 MiB in 3 s" for a Succeeded file with a stored Upload Time (Runs from before it was stored show nothing).</summary>
    public string TransferText => HasTransfer ? TransferFormat.Finished(Bytes, UploadMs!.Value) : "";

    private string AverageText => HasTransfer ? TransferFormat.AverageSpeed(Bytes, UploadMs!.Value) : "";

    /// <summary>The muted line of the Avalonia row: "12.4 MiB in 3 s · 4.1 MiB/s average".</summary>
    public string DetailText => AverageText.Length > 0 ? $"{TransferText} · {AverageText} average" : TransferText;

    /// <summary>The Status cell of the TUI row: the outcome (or reason), then "12.4 MiB in 3 s · 4.1 MiB/s".</summary>
    public string TuiStatusText
    {
        get
        {
            var status = ReasonText.Length > 0 ? ReasonText : OutcomeText;
            if (TransferText.Length == 0) return status;
            return AverageText.Length > 0 ? $"{status} {TransferText} · {AverageText}" : $"{status} {TransferText}";
        }
    }

    /// <summary>The muted line under the path in the Avalonia list: the reason and/or the transfer text.</summary>
    public string DetailLine => ReasonText.Length > 0 && DetailText.Length > 0 ? $"{ReasonText} · {DetailText}" : ReasonText.Length > 0 ? ReasonText : DetailText;
}

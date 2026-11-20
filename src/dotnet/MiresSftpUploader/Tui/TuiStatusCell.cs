using MiresSftpUploader.Core;
using MiresSftpUploader.ViewModels;

namespace MiresSftpUploader.Tui;

/// <summary>
/// The Status cell of a row on the TUI Upload page. While a file uploads and has an Upload Speed (2 samples): <c>███░░░░░ 42% 3.1 MiB/s</c>;
/// when the cell is too narrow the bar goes first and percent and speed stay. A finished file reads <c>Succeeded 12.4 MiB in 3 s</c>.
/// The text comes from the view model (<see cref="UploadProgressViewModel"/>, <see cref="TransferFormat"/>), so the TUI cannot disagree with it.
/// </summary>
public static class TuiStatusCell
{
    /// <summary>Cells of the bar.</summary>
    public const int BarWidth = 8;

    public static string Of(FileRowViewModel row, int width)
    {
        if (row.Outcome == FileOutcome.Uploading && row.Progress is { HasProgress: true } progress) return Uploading(progress, width);
        if (row.Outcome == FileOutcome.Succeeded && row.HasReason) return $"{row.OutcomeText} {row.Reason}";
        return row.HasReason ? row.Reason! : row.OutcomeText;
    }

    private static string Uploading(UploadProgressViewModel progress, int width)
    {
        var text = $"{progress.PercentText} {progress.SpeedText}";
        var filled = (int)(progress.Fraction * BarWidth);
        var withBar = $"{new string('█', filled)}{new string('░', BarWidth - filled)} {text}";
        return width >= withBar.Length ? withBar : text;
    }
}

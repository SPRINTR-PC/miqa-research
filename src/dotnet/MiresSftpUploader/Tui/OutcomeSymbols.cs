using MiresSftpUploader.Core;

namespace MiresSftpUploader.Tui;

/// <summary>The one place that maps an outcome or status to its symbol; symbol and colour carry the outcome together.</summary>
public static class OutcomeSymbols
{
    /// <summary>A file's outcome in the current Run.</summary>
    public static string Of(FileOutcome outcome) => outcome switch
    {
        FileOutcome.Succeeded => "✓",
        FileOutcome.Failed => "✗",
        FileOutcome.Skipped => "⊘",
        FileOutcome.Pending => "…",
        FileOutcome.Hashing => "#",
        FileOutcome.Uploading => "↑",
        FileOutcome.Verifying => "≈",
        _ => "-",
    };

    /// <summary>A Run's status text in the Run list.</summary>
    public static string OfRun(string status) => status switch
    {
        "Running" => "▶", "Succeeded" => "✓", "Cancelled" => "⊘", "Abandoned" => "!", "Failed" => "✗", _ => "-",
    };

    /// <summary>A recorded file outcome of a past Run.</summary>
    public static string OfRecorded(string outcome) => outcome switch
    {
        "Succeeded" => "✓", "Failed" => "✗", "Skipped" => "⊘", "MovedAway" => "→", _ => "…",
    };
}

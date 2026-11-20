using MiresSftpUploader.Core;
using ReactiveUI;

namespace MiresSftpUploader.ViewModels;

/// <summary>One file in the list of the current Run.</summary>
public sealed class FileRowViewModel(string source, string path) : ViewModelBase
{
    private FileOutcome _outcome = FileOutcome.Pending;
    private string? _reason;

    private UploadProgressViewModel? _progress;

    public string Source { get; } = source;
    public string Path { get; } = path;

    public FileOutcome Outcome
    {
        get => _outcome;
        private set
        {
            this.RaiseAndSetIfChanged(ref _outcome, value);
            this.RaisePropertyChanged(nameof(OutcomeText));
            this.RaisePropertyChanged(nameof(IsFailed));
            this.RaisePropertyChanged(nameof(IsSucceeded));
            this.RaisePropertyChanged(nameof(IsActive));
            this.RaisePropertyChanged(nameof(IsMuted));
            this.RaisePropertyChanged(nameof(IconData));
        }
    }

    /// <summary>Why the file is Skipped or Ignored, or what failed; null when there is nothing to say.</summary>
    public string? Reason
    {
        get => _reason;
        private set
        {
            this.RaiseAndSetIfChanged(ref _reason, value);
            this.RaisePropertyChanged(nameof(HasReason));
        }
    }

    public bool HasReason => !string.IsNullOrEmpty(Reason);

    /// <summary>The status icon (a 24x24 filled path): a different shape for each outcome, so the status is not told by colour alone.</summary>
    public string IconData => IconFor(Outcome);

    /// <summary>The status icon of an outcome; the file list and the filter tiles above it use the same ones.</summary>
    public static string IconFor(FileOutcome outcome) => outcome switch
    {
        FileOutcome.Pending => "M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2zM12 20c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8zm.5-13H11v6l5.25 3.15.75-1.23-4.5-2.67z",
        FileOutcome.Hashing => "M20 10V8h-4V4h-2v4h-4V4H8v4H4v2h4v4H4v2h4v4h2v-4h4v4h2v-4h4v-2h-4v-4h4zm-6 4h-4v-4h4v4z",
        FileOutcome.Uploading => "M9 16h6v-6h4l-7-7-7 7h4zm-4 2h14v2H5z",
        FileOutcome.Verifying => "M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm-2 16l-4-4 1.41-1.41L10 14.17l6.59-6.59L18 9l-8 8z",
        FileOutcome.Succeeded => "M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z",
        FileOutcome.Failed => "M12 2C6.47 2 2 6.47 2 12s4.47 10 10 10 10-4.47 10-10S17.53 2 12 2zm5 13.59L15.59 17 12 13.41 8.41 17 7 15.59 10.59 12 7 8.41 8.41 7 12 10.59 15.59 7 17 8.41 13.41 12 17 15.59z",
        FileOutcome.Skipped => "M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z",
        _ => "M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zM4 12c0-4.42 3.58-8 8-8 1.85 0 3.55.63 4.9 1.69L5.69 16.9C4.63 15.55 4 13.85 4 12zm8 8c-1.85 0-3.55-.63-4.9-1.69L18.31 7.1C19.37 8.45 20 10.15 20 12c0 4.42-3.58 8-8 8z",
    };

    public string OutcomeText => Outcome.ToString();
    public bool IsFailed => Outcome == FileOutcome.Failed;
    public bool IsSucceeded => Outcome == FileOutcome.Succeeded;
    public bool IsActive => Outcome is FileOutcome.Hashing or FileOutcome.Uploading or FileOutcome.Verifying;
    public bool IsMuted => Outcome is FileOutcome.Pending or FileOutcome.Skipped or FileOutcome.Ignored;

    /// <summary>
    /// The live bar, percent and Upload Speed while the file uploads; null until the first snapshot (rows are many, so it is created on demand).
    /// Cleared when the file leaves Uploading.
    /// </summary>
    public UploadProgressViewModel? Progress => _progress;

    internal UploadProgressViewModel EnsureProgress() => _progress ??= new UploadProgressViewModel(Source, Path);

    internal void Update(FileOutcome outcome, string? reason)
    {
        Outcome = outcome;
        Reason = reason;
        if (outcome != FileOutcome.Uploading) _progress?.Clear();
    }
}

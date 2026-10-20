using MiresSftpUploader.Core;
using ReactiveUI;

namespace MiresSftpUploader.ViewModels;

/// <summary>One file in the list of the current Run.</summary>
public sealed class FileRowViewModel(string source, string path) : ViewModelBase
{
    private FileOutcome _outcome = FileOutcome.Pending;
    private string? _reason;

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
        }
    }

    /// <summary>Why the file is Skipped or Ignored, or what failed; null when there is nothing to say.</summary>
    public string? Reason
    {
        get => _reason;
        private set => this.RaiseAndSetIfChanged(ref _reason, value);
    }

    public string OutcomeText => Outcome.ToString();
    public bool IsFailed => Outcome == FileOutcome.Failed;
    public bool IsSucceeded => Outcome == FileOutcome.Succeeded;
    public bool IsActive => Outcome is FileOutcome.Hashing or FileOutcome.Uploading or FileOutcome.Verifying;
    public bool IsMuted => Outcome is FileOutcome.Pending or FileOutcome.Skipped or FileOutcome.Ignored;

    internal void Update(FileOutcome outcome, string? reason)
    {
        Outcome = outcome;
        Reason = reason;
    }
}

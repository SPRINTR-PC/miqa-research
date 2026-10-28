namespace MiresSftpUploader.Core;

/// <summary>What a Run covers. <see cref="SourceNames"/> empty means every configured Source.</summary>
public sealed record RunOptions
{
    public IReadOnlyList<string> SourceNames { get; init; } = [];
    public bool DryRun { get; init; }
    /// <summary>Ignore the size and mtime fast path: hash and upload every file again.</summary>
    public bool RehashAll { get; init; }
    /// <summary>Sources whose Upload State is forgotten before the Run, forcing a full re-upload. Never deletes remote files.</summary>
    public IReadOnlyList<string> ResetSources { get; init; } = [];
    public string StartedBy { get; init; } = Environment.UserName;
    /// <summary>How the Run was started; recorded in the Run History.</summary>
    public RunTrigger Trigger { get; init; } = RunTrigger.Headless;
    /// <summary>
    /// The Run whose failed files this Run uploads again, without rescanning the Sources.
    /// A file that has vanished since is marked Missing.
    /// </summary>
    public Guid? RetryOf { get; init; }
    /// <summary>
    /// Where to write this Run's Report (a file, or an existing directory to get the configured file name pattern).
    /// Null means the configured Report directory, and no Report for a Dry Run.
    /// </summary>
    public string? ReportPath { get; init; }
    /// <summary>Report format for this Run; null means the configured one.</summary>
    public ReportFormat? ReportFormat { get; init; }
}

public enum RunTrigger { Headless, Ui, Tui }

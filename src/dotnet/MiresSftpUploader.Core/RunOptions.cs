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
}

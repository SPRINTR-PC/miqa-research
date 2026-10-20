namespace MiresSftpUploader.Core;

/// <summary>What a Run covers. <see cref="SourceNames"/> empty means every configured Source.</summary>
public sealed record RunOptions
{
    public IReadOnlyList<string> SourceNames { get; init; } = [];
    public bool DryRun { get; init; }
    public string StartedBy { get; init; } = Environment.UserName;
}

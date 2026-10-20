namespace MiresSftpUploader.Core;

public sealed record RetrySettings
{
    /// <summary>Total attempts per file, including the first.</summary>
    public int MaxAttempts { get; init; } = 3;
    public TimeSpan BaseDelay { get; init; } = TimeSpan.FromSeconds(2);
    public TimeSpan MaxDelay { get; init; } = TimeSpan.FromSeconds(60);
}

public sealed record EngineSettings
{
    /// <summary>Remote directory under which each Source gets its own directory unless it sets a Remote Path.</summary>
    public string RemoteRoot { get; init; } = "/";
    public int MaxParallelUploads { get; init; } = 3;
    public RetrySettings Retry { get; init; } = new();
    public string ManifestName { get; init; } = "manifest.json";
}

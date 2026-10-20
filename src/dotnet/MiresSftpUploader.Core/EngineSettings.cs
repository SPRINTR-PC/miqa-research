namespace MiresSftpUploader.Core;

public sealed record RetrySettings
{
    /// <summary>Total attempts per file, including the first.</summary>
    public int MaxAttempts { get; init; } = 3;
    public TimeSpan BaseDelay { get; init; } = TimeSpan.FromSeconds(2);
    public TimeSpan MaxDelay { get; init; } = TimeSpan.FromSeconds(60);
}

public sealed record StateSettings
{
    /// <summary>Path of the Upload State database; the lock file lives beside it. Null means no Upload State (every Run uploads everything).</summary>
    public string? Path { get; init; }
    /// <summary>How long per-Run file outcomes are kept.</summary>
    public TimeSpan RunFilesRetention { get; init; } = TimeSpan.FromDays(180);
    /// <summary>How long a Missing file's record is kept.</summary>
    public TimeSpan MissingRetention { get; init; } = TimeSpan.FromDays(90);
    /// <summary>A Run whose heartbeat is older than this is Abandoned.</summary>
    public TimeSpan AbandonedAfter { get; init; } = TimeSpan.FromSeconds(60);
    public TimeSpan HeartbeatInterval { get; init; } = TimeSpan.FromSeconds(10);
}

public sealed record EngineSettings
{
    /// <summary>Remote directory under which each Source gets its own directory unless it sets a Remote Path.</summary>
    public string RemoteRoot { get; init; } = "/";
    /// <summary>host:port of the SFTP server; part of the Upload State key, so a different server counts as new.</summary>
    public string Destination { get; init; } = "";
    public StateSettings State { get; init; } = new();
    public int MaxParallelUploads { get; init; } = 3;
    public RetrySettings Retry { get; init; } = new();
    public string ManifestName { get; init; } = "manifest.json";
}

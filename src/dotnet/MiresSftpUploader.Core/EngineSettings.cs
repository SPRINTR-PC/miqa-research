namespace MiresSftpUploader.Core;

public sealed record RetrySettings
{
    /// <summary>Total attempts per file, including the first.</summary>
    public int MaxAttempts { get; init; } = 3;
    public TimeSpan BaseDelay { get; init; } = TimeSpan.FromSeconds(2);
    public TimeSpan MaxDelay { get; init; } = TimeSpan.FromSeconds(60);
}

public sealed record ReportSettings
{
    /// <summary>Where the Report of each Run is written; null means <c>reports</c> beside the Upload State database.</summary>
    public string? Directory { get; init; }
    /// <summary>Report file name. Tokens: <c>{runId}</c>, <c>{date}</c> (yyyyMMdd, UTC), <c>{time}</c> (HHmmss, UTC), <c>{format}</c> (json or csv).</summary>
    public string FileNamePattern { get; init; } = "run-{runId}.{format}";
    public ReportFormat Format { get; init; } = ReportFormat.Json;
}

public sealed record StateSettings
{
    /// <summary>Path of the Upload State database; the lock file lives beside it. Null means no Upload State (every Run uploads everything).</summary>
    public string? Path { get; init; }
    /// <summary>
    /// Group granted access to the Data Directory on Linux and macOS (default mires-uploader / staff). Machine Config or
    /// environment only; never editable in the UI. Windows always uses BUILTIN\Users.
    /// </summary>
    public string? AccessGroup { get; init; }
    /// <summary>How long per-Run file outcomes are kept.</summary>
    public TimeSpan RunFilesRetention { get; init; } = TimeSpan.FromDays(180);
    /// <summary>How long a Missing file's record is kept.</summary>
    public TimeSpan MissingRetention { get; init; } = TimeSpan.FromDays(90);
    /// <summary>A Run whose heartbeat is older than this is Abandoned.</summary>
    public TimeSpan AbandonedAfter { get; init; } = TimeSpan.FromSeconds(60);
    public TimeSpan HeartbeatInterval { get; init; } = TimeSpan.FromSeconds(10);
    /// <summary>How often a running Engine looks for a cancel request made by another account.</summary>
    public TimeSpan CancelPollInterval { get; init; } = TimeSpan.FromSeconds(1);
    /// <summary>How often <c>RunHistory.WatchRun</c> polls the Upload State.</summary>
    public TimeSpan WatchInterval { get; init; } = TimeSpan.FromSeconds(1);
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
    public ReportSettings Report { get; init; } = new();
    public string ManifestName { get; init; } = "manifest.json";
    /// <summary>Name of the Flat Manifest; always Ignored when it turns up in a Source, like the Manifest.</summary>
    public string FlatManifestName { get; init; } = "manifest.sha256";
    /// <summary>Written into every Manifest as <c>toolVersion</c>; defaults to the AssemblyInformationalVersion shared with the app.</summary>
    public string ToolVersion { get; init; } = typeof(EngineSettings).Assembly
        .GetCustomAttributes(typeof(System.Reflection.AssemblyInformationalVersionAttribute), false)
        .Cast<System.Reflection.AssemblyInformationalVersionAttribute>().FirstOrDefault()?.InformationalVersion ?? "0.0.0";
    /// <summary>Written into every Manifest as <c>machineName</c>.</summary>
    public string MachineName { get; init; } = Environment.MachineName;
    /// <summary>Global Ignore Rules; each Source's own <see cref="SourceConfig.Ignore"/> adds to them.</summary>
    public IgnoreConfig Ignore { get; init; } = new();
    /// <summary>Global Archive Rules and Staging Area settings; each Source's own <see cref="SourceConfig.ArchiveRules"/> are tried first.</summary>
    public ArchiveConfig Archive { get; init; } = new();
    /// <summary>Global Too Recent limits; a Source's own <see cref="SourceConfig.Scan"/> overrides them.</summary>
    public ScanConfig Scan { get; init; } = new();
    /// <summary>Per-Source additions, matched to a Source by name (case-insensitive).</summary>
    public IReadOnlyList<SourceConfig> SourceConfigs { get; init; } = [];
}

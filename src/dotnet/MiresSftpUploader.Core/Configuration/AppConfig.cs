namespace MiresSftpUploader.Core;

public enum AuthMethod { Password, PrivateKey }
public enum RemoteAccess { Auto, ReadWrite, WriteOnly }
public enum UploadStrategy { PartThenRename, Direct }
public enum SourceType { Directory, S3 }
public enum ArchiveGrouping { PerDirectory, PerRule }
public enum VerificationLevel { Off, Size, Hash, ReadBack }
public enum MoveAction { None, Move }
public enum ReportFormat { Json, Csv }
public enum UiTheme { Dark, Light, System }
public enum LogLevelSetting { Trace, Debug, Info, Warn, Error, Fatal }

/// <summary>The effective settings of a Run. Immutable. Never holds a Secret.</summary>
public sealed record AppConfig
{
    public SftpConfig Sftp { get; init; } = new();
    public IReadOnlyList<SourceConfig> Sources { get; init; } = [];
    public IgnoreConfig Ignore { get; init; } = new();
    public ArchiveConfig Archive { get; init; } = new();
    public ScanConfig Scan { get; init; } = new();
    public ManifestConfig Manifest { get; init; } = new();
    public UploadConfig Upload { get; init; } = new();
    public RetryConfig Retry { get; init; } = new();
    public StateConfig State { get; init; } = new();
    public ReportConfig Report { get; init; } = new();
    public LoggingConfig Logging { get; init; } = new();
    public UiConfig Ui { get; init; } = new();
}

public sealed record SftpConfig
{
    public string? Host { get; init; }
    public int Port { get; init; } = 22;
    public string? Username { get; init; }
    public AuthMethod AuthMethod { get; init; } = AuthMethod.Password;
    public string? PrivateKeyPath { get; init; }
    /// <summary>Without the <c>SHA256:</c> or <c>MD5:</c> prefix.</summary>
    public string? HostKeyFingerprint { get; init; }
    public string RemoteRoot { get; init; } = "/";
    public RemoteAccess RemoteAccess { get; init; } = RemoteAccess.Auto;
    public UploadStrategy UploadStrategy { get; init; } = UploadStrategy.PartThenRename;
    public int ConnectTimeoutSeconds { get; init; } = 30;
    public int KeepAliveSeconds { get; init; } = 30;
}

public sealed record SourceConfig
{
    public string? Name { get; init; }
    public SourceType Type { get; init; } = SourceType.Directory;
    public bool Enabled { get; init; } = true;
    public string? RemotePath { get; init; }
    public SourceIgnoreConfig Ignore { get; init; } = new();
    public IReadOnlyList<ArchiveRuleConfig> ArchiveRules { get; init; } = [];
    public SourceScanConfig Scan { get; init; } = new();
    public AfterUploadConfig AfterUpload { get; init; } = new();

    // Directory
    public string? Path { get; init; }
    public bool FollowSymlinks { get; init; }

    // S3
    public string? Endpoint { get; init; }
    public string? Bucket { get; init; }
    public string? Prefix { get; init; }
    public string? Region { get; init; }
    public bool ForcePathStyle { get; init; }
}

public sealed record SourceIgnoreConfig
{
    public IReadOnlyList<string> Files { get; init; } = [];
    public IReadOnlyList<string> Patterns { get; init; } = [];
}

public sealed record SourceScanConfig
{
    public int? MinFileAgeSeconds { get; init; }
    public DateTimeOffset? ModifiedBefore { get; init; }
}

/// <summary>Post-upload Move settings of one Source.</summary>
public sealed record AfterUploadConfig
{
    public MoveTargetConfig OnSuccess { get; init; } = new();
    public MoveTargetConfig OnFailure { get; init; } = new();
}

/// <summary>Same type as the Source: <see cref="Path"/> for a Directory, <see cref="Bucket"/> and <see cref="Prefix"/> for S3.</summary>
public sealed record MoveTargetConfig
{
    public MoveAction Action { get; init; } = MoveAction.None;
    public string? Path { get; init; }
    public string? Bucket { get; init; }
    public string? Prefix { get; init; }
}

public sealed record IgnoreConfig
{
    public bool UseDefaults { get; init; } = true;
    public IReadOnlyList<string> Files { get; init; } = [];
    public IReadOnlyList<string> Patterns { get; init; } = [];
}

public sealed record ArchiveConfig
{
    public string? StagingPath { get; init; }
    public IReadOnlyList<ArchiveRuleConfig> Rules { get; init; } = [];
    public int MaxParallelBuilds { get; init; } = 1;
    public long WarnAboveBytes { get; init; } = 50L * 1024 * 1024 * 1024;
}

public sealed record ArchiveRuleConfig
{
    public string? Name { get; init; }
    public string? Pattern { get; init; }
    public ArchiveGrouping Grouping { get; init; } = ArchiveGrouping.PerDirectory;
    /// <summary>Template with <c>{rule}</c>, <c>{dir}</c> and <c>{date}</c>.</summary>
    public string ArchiveName { get; init; } = "{rule}-{dir}.zip";
    public int MinFiles { get; init; } = 1;
}

public sealed record ScanConfig
{
    public int MinFileAgeSeconds { get; init; }
    public DateTimeOffset? ModifiedBefore { get; init; }
}

public sealed record ManifestConfig
{
    public string JsonName { get; init; } = "manifest.json";
    public string FlatName { get; init; } = "manifest.sha256";
    public bool WriteFlat { get; init; }
    public string InProgressSuffix { get; init; } = ".inprogress";
}

public sealed record UploadConfig
{
    public int MaxParallelUploads { get; init; } = 3;
    public VerificationLevel VerifyAfterUpload { get; init; } = VerificationLevel.Off;
    public bool RehashAll { get; init; }
    public VerificationLevel VerifyRemote { get; init; } = VerificationLevel.Off;
    public const string DefaultVerifyCommand = "sha256sum -- {path}";
    /// <summary>
    /// Command the Hash level runs on the server; <c>{path}</c> is replaced by the shell-quoted remote path. Machine Config or
    /// environment only: User Overrides and the UI cannot set it, so a user cannot make a scheduled Run execute a command of their choice.
    /// </summary>
    public string VerifyCommand { get; init; } = DefaultVerifyCommand;
    /// <summary>Longest a single file's Verification may take.</summary>
    public int VerifyTimeoutSeconds { get; init; } = 3600;
    public bool MoveFailuresAreErrors { get; init; }
}

public sealed record RetryConfig
{
    public int MaxAttempts { get; init; } = 3;
    public int BaseDelaySeconds { get; init; } = 2;
    public int MaxDelaySeconds { get; init; } = 60;
}

public sealed record StateConfig
{
    /// <summary>Data Directory override; empty means the machine-wide default.</summary>
    public string? Path { get; init; }
    /// <summary>
    /// Group granted access to the Data Directory on Linux and macOS (default mires-uploader / staff; Windows uses BUILTIN\Users).
    /// Machine Config or environment only: User Overrides and the UI cannot set it.
    /// </summary>
    public string? AccessGroup { get; init; }
    public int RunFilesRetentionDays { get; init; } = 180;
    public int MissingRetentionDays { get; init; } = 90;
    public int HeartbeatSeconds { get; init; } = 15;
    public int StaleAfterSeconds { get; init; } = 60;
    public int CancelPollSeconds { get; init; } = 5;
}

public sealed record ReportConfig
{
    public string? Directory { get; init; }
    public ReportFormat Format { get; init; } = ReportFormat.Json;
    public string FileNamePattern { get; init; } = "run-{runId}.{format}";
}

public sealed record LoggingConfig
{
    public LogLevelSetting Level { get; init; } = LogLevelSetting.Info;
    /// <summary>Empty means <c>&lt;per-user app data&gt;/logs</c>.</summary>
    public string? Directory { get; init; }
    public int RetainDays { get; init; } = 14;
    /// <summary>Unset means on for a Headless Run and off for the UI.</summary>
    public bool? Console { get; init; }
}

public sealed record UiConfig
{
    public UiTheme Theme { get; init; } = UiTheme.Dark;
    public LogLevelSetting LogLevel { get; init; } = LogLevelSetting.Info;
}

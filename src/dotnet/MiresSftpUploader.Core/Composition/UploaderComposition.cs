namespace MiresSftpUploader.Core;

/// <summary>
/// Maps the effective <see cref="AppConfig"/> onto what the Engine and the Run History take. The one place that
/// does this mapping, shared by the window and the Headless Run.
/// </summary>
public static class UploaderComposition
{
    /// <summary>File name of the Upload State database inside the Data Directory (the lock file lives beside it).</summary>
    public const string DatabaseFileName = "upload-state.db";

    public static EngineSettings ToEngineSettings(AppConfig config) => new()
    {
        RemoteRoot = config.Sftp.RemoteRoot,
        Destination = DestinationKey(config.Sftp),
        State = ToStateSettings(config),
        MaxParallelUploads = config.Upload.MaxParallelUploads,
        Retry = new RetrySettings
        {
            MaxAttempts = config.Retry.MaxAttempts,
            BaseDelay = TimeSpan.FromSeconds(config.Retry.BaseDelaySeconds),
            MaxDelay = TimeSpan.FromSeconds(config.Retry.MaxDelaySeconds),
        },
        Report = new ReportSettings
        {
            Directory = string.IsNullOrWhiteSpace(config.Report.Directory) ? null : config.Report.Directory,
            FileNamePattern = config.Report.FileNamePattern,
            Format = config.Report.Format,
        },
        ManifestName = config.Manifest.JsonName,
        FlatManifestName = config.Manifest.FlatName,
        Ignore = config.Ignore,
        Scan = config.Scan,
        SourceConfigs = config.Sources,
    };

    /// <summary>
    /// The Upload State settings. <c>State:Path</c> is the Data Directory; without one there is no Upload State
    /// (and so no Run History). The Data Directory ticket replaces the "none" with the per-OS default.
    /// </summary>
    public static StateSettings ToStateSettings(AppConfig config) => new()
    {
        Path = string.IsNullOrWhiteSpace(config.State.Path) ? null : Path.Combine(config.State.Path, DatabaseFileName),
        RunFilesRetention = TimeSpan.FromDays(config.State.RunFilesRetentionDays),
        MissingRetention = TimeSpan.FromDays(config.State.MissingRetentionDays),
        HeartbeatInterval = TimeSpan.FromSeconds(config.State.HeartbeatSeconds),
        AbandonedAfter = TimeSpan.FromSeconds(config.State.StaleAfterSeconds),
        CancelPollInterval = TimeSpan.FromSeconds(config.State.CancelPollSeconds),
    };

    /// <summary>host:port, the key the Upload State is filed under.</summary>
    public static string DestinationKey(SftpConfig sftp) =>
        string.IsNullOrWhiteSpace(sftp.Host) ? "" : $"{sftp.Host}:{sftp.Port}";
}

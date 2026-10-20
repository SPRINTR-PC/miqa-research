namespace MiresSftpUploader.Core;

/// <summary>
/// Maps the effective <see cref="AppConfig"/> onto what the Engine and the Run History take. The one place that
/// does this mapping, shared by the window and the Headless Run.
/// </summary>
public static class UploaderComposition
{
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
        RemoteAccess = config.Sftp.RemoteAccess,
        UploadStrategy = config.Sftp.UploadStrategy,
        Verification = new VerificationSettings
        {
            AfterUpload = config.Upload.VerifyAfterUpload,
            Remote = config.Upload.VerifyRemote,
            Command = config.Upload.VerifyCommand,
            Timeout = TimeSpan.FromSeconds(config.Upload.VerifyTimeoutSeconds),
        },
        ManifestName = config.Manifest.JsonName,
        FlatManifestName = config.Manifest.FlatName,
        WriteFlatManifest = config.Manifest.WriteFlat,
        InProgressSuffix = config.Manifest.InProgressSuffix,
        Archive = config.Archive,
        Ignore = config.Ignore,
        Scan = config.Scan,
        SourceConfigs = config.Sources,
    };

    /// <summary>
    /// The Upload State settings. <c>State:Path</c> is the Data Directory (<c>MIRES_DATA_DIR</c> and <c>--data-dir</c> set it);
    /// when none is configured the per-OS default is used.
    /// </summary>
    public static StateSettings ToStateSettings(AppConfig config) => new()
    {
        Path = DataDirectory.DatabasePath(DataDirectory.Resolve(
            config.State.Path, null, DataDirectory.CurrentPlatform,
            Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData))),
        AccessGroup = config.State.AccessGroup,
        RunFilesRetention = TimeSpan.FromDays(config.State.RunFilesRetentionDays),
        MissingRetention = TimeSpan.FromDays(config.State.MissingRetentionDays),
        HeartbeatInterval = TimeSpan.FromSeconds(config.State.HeartbeatSeconds),
        AbandonedAfter = TimeSpan.FromSeconds(config.State.StaleAfterSeconds),
        CancelPollInterval = TimeSpan.FromSeconds(config.State.CancelPollSeconds),
    };

    /// <summary>The Upload State settings of the effective configuration, for <c>--list-runs</c> and <c>--export-run</c>; null when the configuration cannot be loaded.</summary>
    public static StateSettings? LoadStateSettings(Configuration configuration, CliOptions cli) =>
        configuration.Load(cli, headless: true).Config is { } config ? ToStateSettings(config) : null;

    /// <summary>host:port, the key the Upload State is filed under.</summary>
    public static string DestinationKey(SftpConfig sftp) =>
        string.IsNullOrWhiteSpace(sftp.Host) ? "" : $"{sftp.Host}:{sftp.Port}";
}

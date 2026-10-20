using MiresSftpUploader.Core;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class CompositionSettingsTests
{
    private static readonly AppConfig Config = new()
    {
        Sftp = new SftpConfig { Host = "sftp.mires.example", Port = 2222, RemoteRoot = "/incoming" },
        Ignore = new IgnoreConfig { UseDefaults = false, Files = ["a.txt"], Patterns = ["\\.tmp$"] },
        Scan = new ScanConfig { MinFileAgeSeconds = 90 },
        Sources = [new SourceConfig { Name = "wsi", Path = "/data/wsi", RemotePath = "/x" }],
        Manifest = new ManifestConfig { JsonName = "m.json", FlatName = "m.sha256" },
        Upload = new UploadConfig { MaxParallelUploads = 5 },
        Retry = new RetryConfig { MaxAttempts = 4, BaseDelaySeconds = 3, MaxDelaySeconds = 90 },
        State = new StateConfig
        {
            Path = "/shared/mires",
            RunFilesRetentionDays = 30,
            MissingRetentionDays = 10,
            HeartbeatSeconds = 15,
            StaleAfterSeconds = 60,
            CancelPollSeconds = 5,
            AccessGroup = "mires-uploader",
        },
        Report = new ReportConfig { Directory = "/reports", Format = ReportFormat.Csv, FileNamePattern = "r-{runId}.{format}" },
    };

    [TestMethod]
    public void Engine_settings_carry_the_destination_retry_names_and_rules_from_the_configuration()
    {
        var settings = UploaderComposition.ToEngineSettings(Config);

        Assert.AreEqual("sftp.mires.example:2222", settings.Destination);
        Assert.AreEqual("/incoming", settings.RemoteRoot);
        Assert.AreEqual(5, settings.MaxParallelUploads);
        Assert.AreEqual(4, settings.Retry.MaxAttempts);
        Assert.AreEqual(TimeSpan.FromSeconds(3), settings.Retry.BaseDelay);
        Assert.AreEqual(TimeSpan.FromSeconds(90), settings.Retry.MaxDelay);
        Assert.AreEqual("m.json", settings.ManifestName);
        Assert.AreEqual("m.sha256", settings.FlatManifestName);
        Assert.IsFalse(settings.Ignore.UseDefaults);
        CollectionAssert.AreEqual(new[] { "\\.tmp$" }, settings.Ignore.Patterns.ToArray());
        Assert.AreEqual(90, settings.Scan.MinFileAgeSeconds);
        Assert.HasCount(1, settings.SourceConfigs);
        Assert.AreEqual("/reports", settings.Report.Directory);
        Assert.AreEqual(ReportFormat.Csv, settings.Report.Format);
        Assert.AreEqual("r-{runId}.{format}", settings.Report.FileNamePattern);
    }

    [TestMethod]
    public void Engine_settings_carry_the_remaining_Manifest_Verification_Archive_and_access_settings()
    {
        var config = Config with
        {
            Sftp = Config.Sftp with { RemoteAccess = RemoteAccess.WriteOnly, UploadStrategy = UploadStrategy.Direct },
            Manifest = new ManifestConfig { JsonName = "m.json", FlatName = "m.sha256", WriteFlat = true, InProgressSuffix = ".busy" },
            Upload = new UploadConfig
            {
                VerifyAfterUpload = VerificationLevel.Size,
                VerifyRemote = VerificationLevel.ReadBack,
                VerifyCommand = "shasum -a 256 {path}",
                VerifyTimeoutSeconds = 90,
            },
            Archive = new ArchiveConfig { StagingPath = "/stage", MaxParallelBuilds = 2, MinFreeSpaceBytes = 5, WarnAboveBytes = 7 },
        };

        var settings = UploaderComposition.ToEngineSettings(config);

        Assert.AreEqual(RemoteAccess.WriteOnly, settings.RemoteAccess);
        Assert.AreEqual(UploadStrategy.Direct, settings.UploadStrategy);
        Assert.IsTrue(settings.WriteFlatManifest);
        Assert.AreEqual(".busy", settings.InProgressSuffix);
        Assert.AreEqual(VerificationLevel.Size, settings.Verification.AfterUpload);
        Assert.AreEqual(VerificationLevel.ReadBack, settings.Verification.Remote);
        Assert.AreEqual("shasum -a 256 {path}", settings.Verification.Command);
        Assert.AreEqual(TimeSpan.FromSeconds(90), settings.Verification.Timeout);
        Assert.AreEqual("/stage", settings.Archive.StagingPath);
        Assert.AreEqual(2, settings.Archive.MaxParallelBuilds);
        Assert.AreEqual(5, settings.Archive.MinFreeSpaceBytes);
        Assert.AreEqual(7, settings.Archive.WarnAboveBytes);
    }

    [TestMethod]
    public void Engine_settings_hold_the_Upload_State_settings_with_seconds_and_days_as_time_spans()
    {
        var state = UploaderComposition.ToEngineSettings(Config).State;

        Assert.AreEqual(DataDirectory.DatabasePath("/shared/mires"), state.Path);
        Assert.AreEqual("mires-uploader", state.AccessGroup);
        Assert.AreEqual(TimeSpan.FromDays(30), state.RunFilesRetention);
        Assert.AreEqual(TimeSpan.FromDays(10), state.MissingRetention);
        Assert.AreEqual(TimeSpan.FromSeconds(15), state.HeartbeatInterval);
        Assert.AreEqual(TimeSpan.FromSeconds(60), state.AbandonedAfter);
        Assert.AreEqual(TimeSpan.FromSeconds(5), state.CancelPollInterval);
    }

    [TestMethod]
    public void No_Data_Directory_configured_means_the_per_OS_default()
    {
        var state = UploaderComposition.ToStateSettings(new AppConfig());

        var expected = DataDirectory.Resolve(null, null, DataDirectory.CurrentPlatform, Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData));
        Assert.AreEqual(DataDirectory.DatabasePath(expected), state.Path);
    }

    [TestMethod]
    public void The_real_SFTP_adapter_is_the_default_remote()
    {
        var remote = new SshNetRemoteFactory().Create(new AppConfig { Sftp = new SftpConfig { Host = "h", Username = "u", HostKeyFingerprint = "abc" } }, new Configuration(new ConfigurationLocations("", "", new Dictionary<string, string?>())).LoadSecrets());

        Assert.IsInstanceOfType<SshNetRemote>(remote);
    }
}

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
    public void Engine_settings_hold_the_Upload_State_settings_with_seconds_and_days_as_time_spans()
    {
        var state = UploaderComposition.ToEngineSettings(Config).State;

        Assert.AreEqual(Path.Combine("/shared/mires", "upload-state.db"), state.Path);
        Assert.AreEqual(TimeSpan.FromDays(30), state.RunFilesRetention);
        Assert.AreEqual(TimeSpan.FromDays(10), state.MissingRetention);
        Assert.AreEqual(TimeSpan.FromSeconds(15), state.HeartbeatInterval);
        Assert.AreEqual(TimeSpan.FromSeconds(60), state.AbandonedAfter);
        Assert.AreEqual(TimeSpan.FromSeconds(5), state.CancelPollInterval);
    }

    [TestMethod]
    public void No_Data_Directory_configured_means_no_Upload_State()
    {
        var state = UploaderComposition.ToStateSettings(new AppConfig());

        Assert.IsNull(state.Path);
    }
}

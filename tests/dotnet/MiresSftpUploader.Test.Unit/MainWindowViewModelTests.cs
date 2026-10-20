using System.Reactive.Threading.Tasks;
using Microsoft.Extensions.Logging;
using MiresSftpUploader.Core;
using MiresSftpUploader.Logging;
using MiresSftpUploader.Test.Support;
using MiresSftpUploader.ViewModels;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class MainWindowViewModelTests
{
    private readonly List<UiTheme> _saved = [];
    private string? _saveError;

    private MainWindowViewModel NewWindow(UiTheme theme = UiTheme.Dark, LogPaneViewModel? log = null)
    {
        var upload = new UploadPageViewModel(new FakeUploaderRuntime(new AppConfig(), new FakeRunEngine()), a => a());
        return new MainWindowViewModel(upload, log, theme, t => { _saved.Add(t); return _saveError; });
    }

    [TestMethod]
    public void Toggling_the_theme_switches_between_dark_and_light_and_saves_it_to_User_Overrides()
    {
        var window = NewWindow(UiTheme.Dark);
        Assert.IsTrue(window.IsDark);

        window.ToggleThemeCommand.Execute().Subscribe();
        Assert.AreEqual(UiTheme.Light, window.Theme);
        Assert.IsFalse(window.IsDark);

        window.ToggleThemeCommand.Execute().Subscribe();
        Assert.AreEqual(UiTheme.Dark, window.Theme);
        CollectionAssert.AreEqual(new[] { UiTheme.Light, UiTheme.Dark }, _saved);
    }

    [TestMethod]
    public void The_toggle_is_labelled_with_the_theme_it_switches_to()
    {
        var window = NewWindow(UiTheme.Dark);
        Assert.AreEqual("Light theme", window.ThemeToggleLabel);

        window.ToggleThemeCommand.Execute().Subscribe();
        Assert.AreEqual("Dark theme", window.ThemeToggleLabel);
    }

    [TestMethod]
    public void A_theme_that_cannot_be_saved_still_switches_for_this_session_and_says_why()
    {
        _saveError = "Ui:Theme is a locked setting.";
        var window = NewWindow(UiTheme.Dark);

        window.ToggleThemeCommand.Execute().Subscribe();

        Assert.AreEqual(UiTheme.Light, window.Theme);
        StringAssert.Contains(window.ThemeNotice, "locked");
    }

    [TestMethod]
    public void With_the_System_theme_the_toggle_picks_the_opposite_of_the_system_theme()
    {
        var window = NewWindow(UiTheme.System);
        window.SystemIsDark = true;
        Assert.IsTrue(window.IsDark);

        window.ToggleThemeCommand.Execute().Subscribe();

        Assert.AreEqual(UiTheme.Light, window.Theme);
    }

    [TestMethod]
    public void The_sidebar_opens_Settings_and_Help_and_returns_to_Upload()
    {
        var window = NewWindow();
        Assert.AreEqual(AppPage.Upload, window.Page);

        window.ShowSettingsCommand.Execute().Subscribe();
        Assert.AreEqual(AppPage.Settings, window.Page);
        window.ShowHelpCommand.Execute().Subscribe();
        Assert.AreEqual(AppPage.Help, window.Page);
        window.ShowUploadCommand.Execute().Subscribe();
        Assert.AreEqual(AppPage.Upload, window.Page);
    }

    [TestMethod]
    public void The_sidebar_opens_History_which_reads_the_Run_History_again()
    {
        var history = new FakeRunHistory();
        var engine = new FakeRunEngine();
        var upload = new UploadPageViewModel(new FakeUploaderRuntime(new AppConfig(), engine), a => a());
        var historyPage = new HistoryPageViewModel(history, "anna", a => a(), _ => Task.CompletedTask);
        var window = new MainWindowViewModel(upload, null, UiTheme.Dark, _ => null, historyPage);
        history.Add();
        Assert.IsEmpty(historyPage.Runs);

        window.ShowHistoryCommand.Execute().Subscribe();

        Assert.AreEqual(AppPage.History, window.Page);
        Assert.IsTrue(window.IsHistoryPage);
        Assert.HasCount(1, historyPage.Runs);
    }

    [TestMethod]
    public async Task Retrying_from_History_switches_to_the_Upload_page_and_starts_the_Retry()
    {
        var history = new FakeRunHistory();
        var engine = new FakeRunEngine();
        var upload = new UploadPageViewModel(new FakeUploaderRuntime(new AppConfig { Sources = [new SourceConfig { Name = "wsi", Path = "/d" }] }, engine), a => a());
        MainWindowViewModel? window = null;
        var historyPage = new HistoryPageViewModel(history, "anna", a => a(), id => window!.RetryFromHistoryAsync(id));
        window = new MainWindowViewModel(upload, null, UiTheme.Dark, _ => null, historyPage);
        var failed = history.Add(exitCode: 1, counts: new Dictionary<string, int> { ["Failed"] = 1 });
        window.ShowHistoryCommand.Execute().Subscribe();

        await historyPage.Runs[0].RetryCommand.Execute().ToTask();

        Assert.AreEqual(AppPage.Upload, window.Page);
        Assert.AreEqual(failed.Summary.RunId, engine.Calls.Single().RetryOf);
    }

    [TestMethod]
    public void Without_a_log_target_there_is_no_log_pane()
    {
        Assert.IsFalse(NewWindow(log: null).HasLog);
    }

    [TestMethod]
    public void The_log_pane_is_shown_when_there_is_a_log_target_and_filters_by_level()
    {
        var target = new UiLogTarget();
        var log = new LogPaneViewModel(target, a => a(), LogLevel.Information);
        var window = NewWindow(log: log);

        Assert.IsTrue(window.HasLog);
        target.Emit(new LogEntry(DateTimeOffset.UnixEpoch, LogLevel.Debug, "t", "quiet"));
        target.Emit(new LogEntry(DateTimeOffset.UnixEpoch, LogLevel.Warning, "t", "loud"));
        CollectionAssert.AreEqual(new[] { "loud" }, log.Entries.Select(e => e.Message).ToArray());

        log.MinimumLevel = LogLevel.Debug;
        Assert.HasCount(2, log.Entries);
        CollectionAssert.AreEqual(
            new[] { LogLevel.Debug, LogLevel.Information, LogLevel.Warning, LogLevel.Error },
            LogPaneViewModel.SelectableLevels.ToArray());
    }

    [TestMethod]
    public void A_Data_Directory_that_is_not_writable_blocks_the_Upload_page_and_re_checking_unblocks_it()
    {
        var writable = false;
        var cfg = SettingsFixture.Create(out var dir);
        var settings = new SettingsPageViewModel(cfg, path => new DataDirectoryAccess(path, true, writable, "alice", null, 0, 0, false, "fix it", writable ? null : "not writable"), _ => long.MaxValue);
        var upload = new UploadPageViewModel(new FakeUploaderRuntime(new AppConfig(), new FakeRunEngine()), a => a());

        var window = new MainWindowViewModel(upload, null, UiTheme.Dark, _ => null, settings: settings);

        Assert.IsTrue(window.Upload.IsBlocked);
        StringAssert.Contains(window.Upload.BlockedReason, "not writable");

        writable = true;
        settings.RecheckDataDirectoryCommand.Execute().Subscribe();

        Assert.IsFalse(window.Upload.IsBlocked);
        Directory.Delete(dir, true);
    }

    [TestMethod]
    public void Saving_Settings_refreshes_the_Upload_page_and_applies_the_theme()
    {
        var cfg = SettingsFixture.Create(out var dir);
        var settings = new SettingsPageViewModel(cfg, path => new DataDirectoryAccess(path, true, true, "alice", null, 0, 0, false, "", null), _ => long.MaxValue);
        var runtime = new FakeUploaderRuntime(new AppConfig(), new FakeRunEngine());
        var upload = new UploadPageViewModel(runtime, a => a());
        var window = new MainWindowViewModel(upload, null, UiTheme.Dark, _ => null, settings: settings);
        var prepared = runtime.PrepareCount;

        settings.Field("Ui:Theme").Value = "Light";
        settings.Field("Sftp:Host").Value = "sftp.example.org";
        settings.Field("Sftp:Username").Value = "u";
        settings.Field("Sftp:HostKeyFingerprint").Value = "abc";
        settings.AddSourceCommand.Execute().Subscribe();
        settings.Sources[0].Name = "alpha";
        settings.Sources[0].Path = dir;
        settings.SaveCommand.Execute().Subscribe();

        Assert.AreEqual(UiTheme.Light, window.Theme, settings.SaveMessage + string.Join("|", settings.OtherErrors));
        Assert.IsGreaterThan(prepared, runtime.PrepareCount);
        Directory.Delete(dir, true);
    }
}

internal static class SettingsFixture
{
    public static Configuration Create(out string dir)
    {
        dir = Path.Combine(Path.GetTempPath(), "mires-settings-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(Path.Combine(dir, "install"));
        File.WriteAllText(Path.Combine(dir, "install", "appsettings.json"), "{}");
        return new Configuration(new ConfigurationLocations(Path.Combine(dir, "install", "appsettings.json"), Path.Combine(dir, "user", "appsettings.user.json"), new Dictionary<string, string?>()));
    }
}

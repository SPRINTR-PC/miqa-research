using MiresSftpUploader.Core;
using MiresSftpUploader.SettingsTui;
using MiresSftpUploader.Test.Support;
using MiresSftpUploader.Tui;
using MiresSftpUploader.ViewModels;
using Terminal.Gui.Input;

namespace MiresSftpUploader.Test.Unit;

/// <summary>Retry from History across the pages of the whole-app TUI: the hand-off to Upload, the notice while a Run is active, the lock refusal.</summary>
[TestClass]
public sealed class HistoryTuiRetryTests : ConfigurationTestBase
{
    private static readonly AppConfig Config = new() { Sources = [new SourceConfig { Name = "wsi", Path = "/data/wsi" }] };

    private readonly List<TuiTestHost> _hosts = [];
    private readonly FakeRunHistory _history = new();

    [TestCleanup]
    public void CloseHosts()
    {
        foreach (var h in _hosts) h.Dispose();
    }

    private sealed record Started(TuiTestHost Host, TuiShell Shell, UploadPageViewModel Upload, HistoryPageViewModel History, FakeRunEngine Engine, FakeTuiDialogs Dialogs);

    private Started Start(FakeRunEngine engine)
    {
        var settings = new SettingsPageViewModel(Create(ValidMachine().ToJsonString()));
        var dialogs = new FakeTuiDialogs();
        TuiShell? shell = null;
        UploadPageViewModel? upload = null;
        HistoryPageViewModel? history = null;
        var host = new TuiTestHost(app =>
        {
            upload = new UploadPageViewModel(new FakeUploaderRuntime(Config, engine), a => app.Invoke(a), RunTrigger.Tui);
            history = new HistoryPageViewModel(_history, "anna", a => app.Invoke(a), id => shell!.RetryFromHistoryAsync(id, upload));
            var uploadPage = new UploadTuiPage(app, upload, log: null, dialogs);
            var historyPage = new HistoryTuiPage(history, a => app.Invoke(a));
            shell = new TuiShell(app, settings, dialogs, ShellTab.History, uploadPage, historyPage);
            shell.CancelWait = TimeSpan.FromSeconds(3);
            return shell;
        }, 100, 32);
        _hosts.Add(host);
        host.WaitUntil(() => shell!.IsInitialized && shell.Current == ShellTab.History, "History shown");
        return new Started(host, shell!, upload!, history!, engine, dialogs);
    }

    private RunDetail SeedFailed() => _history.Add(exitCode: 1, startedBy: "anna",
        counts: new Dictionary<string, int> { ["Succeeded"] = 1, ["Failed"] = 1 },
        files: [new("wsi", "ok.svs", "Succeeded", 1, 1, null), new("wsi", "bad.svs", "Failed", 1, 1, "Connection reset")]);

    [TestMethod, Timeout(60000)]
    public void R_on_a_failed_Run_switches_to_Upload_and_starts_a_Retry_Run_at_once()
    {
        var failed = SeedFailed();
        var engine = new FakeRunEngine { Hold = true };
        var s = Start(engine);

        s.Host.Press(Key.R);

        s.Host.WaitUntil(() => s.Shell.Current == ShellTab.Upload && engine.Calls.Count == 1, "Upload shown with the Retry Run started");
        var options = engine.Calls.Single();
        Assert.AreEqual(failed.Summary.RunId, options.RetryOf);
        Assert.AreEqual(RunTrigger.Tui, options.Trigger);
        Assert.IsFalse(options.DryRun);
        s.Host.WaitUntil(() => s.Upload.IsRunning, "the Run is active");
        engine.Release();
        s.Host.WaitUntilShows("Run finished, exit code 0");
    }

    [TestMethod, Timeout(60000)]
    public void R_while_a_Run_is_active_shows_a_notice_on_History_and_does_not_switch_or_start_a_Run()
    {
        SeedFailed();
        var engine = new FakeRunEngine { Hold = true };
        var s = Start(engine);
        s.Host.Press(Key.F9);
        s.Host.Press(Key.R);
        s.Host.WaitUntil(() => engine.Started.IsCompleted && s.Upload.IsRunning, "a Run is active");
        s.Host.Press(Key.F10);
        s.Host.WaitUntil(() => s.Shell.Current == ShellTab.History, "History shown");

        s.Host.Press(Key.R);

        s.Host.WaitUntilShows("A Run is active; follow it on Upload");
        Assert.AreEqual(ShellTab.History, s.Shell.Current);
        Assert.HasCount(1, engine.Calls);
        engine.Release();
        s.Host.WaitUntil(() => !s.Upload.IsRunning, "the Run ended");
    }

    [TestMethod, Timeout(60000)]
    public void A_Run_lock_held_by_another_process_hands_off_and_the_refusal_shows_on_Upload()
    {
        SeedFailed();
        var engine = new FakeRunEngine { ExitCode = ExitCodes.LockHeld, Reason = "Another Run holds the lock (pid=7 user=ann since=today)" };
        var s = Start(engine);

        s.Host.Press(Key.R);

        s.Host.WaitUntil(() => s.Dialogs.Messages.Count == 1, "the refusal message");
        Assert.AreEqual(ShellTab.Upload, s.Shell.Current);
        StringAssert.Contains(s.Dialogs.Messages[0].Message, "pid=7 user=ann");
        s.Host.WaitUntilShows("Another Run holds the lock");
    }

    [TestMethod, Timeout(60000)]
    public void A_lock_refusal_arriving_while_another_page_is_shown_brings_Upload_forward()
    {
        SeedFailed();
        var engine = new FakeRunEngine { ExitCode = ExitCodes.LockHeld, Reason = "Another Run holds the lock (pid=7)", Hold = true };
        var s = Start(engine);
        s.Host.Press(Key.R);
        s.Host.WaitUntil(() => engine.Started.IsCompleted && s.Upload.IsRunning, "the Retry Run is waiting");
        s.Host.Press(Key.F12);
        s.Host.WaitUntil(() => s.Shell.Current == ShellTab.Help, "Help shown");

        engine.Release();

        s.Host.WaitUntil(() => s.Dialogs.Messages.Count == 1, "the refusal message");
        Assert.AreEqual(ShellTab.Upload, s.Shell.Current);
    }

    [TestMethod, Timeout(60000)]
    public void Switching_tabs_mid_Run_keeps_the_Run_and_the_Upload_filter_and_follow_flag()
    {
        SeedFailed();
        var engine = new FakeRunEngine { Hold = true };
        engine.Script.Add(new FileOutcomeChanged("wsi", "a.ndpi", FileOutcome.Succeeded, null));
        engine.Script.Add(new FileOutcomeChanged("wsi", "b.ndpi", FileOutcome.Uploading, null));
        var s = Start(engine);
        s.Host.Press(Key.R);
        s.Host.WaitUntil(() => s.Shell.Current == ShellTab.Upload && engine.Started.IsCompleted, "Retry Run reported its events");
        s.Host.WaitUntil(() => s.Host.App.Navigation?.GetFocused() is Terminal.Gui.Views.TableView, "focus on the Upload table");
        s.Host.Press(Key.D1);
        s.Host.WaitUntil(() => s.Upload.Filter == FileFilter.Succeeded, "Succeeded filter on");
        var filter = s.Host.OnUi(() => s.Upload.Filter);
        s.Host.OnUi(() => s.Upload.IsFollowing = false);

        s.Host.Press(Key.F10);
        s.Host.WaitUntil(() => s.Shell.Current == ShellTab.History, "History shown");
        s.Host.Press(Key.F9);
        s.Host.WaitUntil(() => s.Shell.Current == ShellTab.Upload, "Upload shown");

        Assert.IsTrue(s.Host.OnUi(() => s.Upload.IsRunning), "the Run is still going");
        Assert.AreEqual(filter, s.Host.OnUi(() => s.Upload.Filter));
        Assert.IsFalse(s.Host.OnUi(() => s.Upload.IsFollowing));
        engine.Release();
        s.Host.WaitUntil(() => !s.Upload.IsRunning, "the Run ended");
    }
}

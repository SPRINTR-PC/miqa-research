using System.Diagnostics;
using Microsoft.Extensions.Logging;
using MiresSftpUploader.Core;
using MiresSftpUploader.Logging;
using MiresSftpUploader.SettingsTui;
using MiresSftpUploader.Test.Support;
using MiresSftpUploader.Tui;
using MiresSftpUploader.ViewModels;
using Terminal.Gui.Input;
using Terminal.Gui.Views;

namespace MiresSftpUploader.Test.Unit;

/// <summary>The toggleable Log pane of the Upload page, on the real <see cref="LogPaneViewModel"/>.</summary>
[TestClass]
public sealed class UploadTuiLogPaneTests : ConfigurationTestBase
{
    private static readonly AppConfig Config = new()
    {
        Sftp = new SftpConfig { Host = "sftp.mires.example", Port = 22 },
        Sources = [new SourceConfig { Name = "wsi", Path = "/data/wsi" }],
    };

    private readonly List<TuiTestHost> _hosts = [];

    [TestCleanup]
    public void CloseHosts()
    {
        foreach (var h in _hosts) h.Dispose();
    }

    private sealed record Started(TuiTestHost Host, UploadTuiPage Page, UploadPageViewModel Vm, UiLogTarget Target, LogPaneViewModel Log, FakeRunEngine Engine);

    private Started Start(int width = 80, int height = 24, int files = 40)
    {
        var engine = new FakeRunEngine { Hold = true };
        for (var i = 0; i < files; i++)
            engine.Script.Add(new FileOutcomeChanged("wsi", $"f{i:D5}.ndpi", FileOutcome.Pending, null));
        var target = new UiLogTarget();
        var settings = new SettingsPageViewModel(Create(ValidMachine().ToJsonString()), WritableDataDirectory.Check, _ => long.MaxValue);
        var dialogs = new FakeTuiDialogs();
        TuiShell? shell = null;
        UploadTuiPage? page = null;
        UploadPageViewModel? vm = null;
        LogPaneViewModel? log = null;
        var host = new TuiTestHost(app =>
        {
            vm = new UploadPageViewModel(new FakeUploaderRuntime(Config, engine), a => app.Invoke(a), RunTrigger.Tui);
            log = new LogPaneViewModel(target, a => app.Invoke(a), LogLevel.Information);
            page = new UploadTuiPage(app, vm, log, dialogs);
            shell = new TuiShell(app, settings, dialogs, ShellTab.Upload, page);
            return shell;
        }, width, height);
        _hosts.Add(host);
        host.WaitUntil(() => shell!.IsInitialized, "shell initialised");
        host.WaitUntil(() => host.App.Navigation?.GetFocused() is TableView, "focus on the table");
        return new Started(host, page!, vm!, target, log!, engine);
    }

    private static void Emit(Started s, string message, LogLevel level = LogLevel.Information) =>
        s.Target.Emit(new LogEntry(DateTimeOffset.UnixEpoch, level, "Test", message));

    /// <summary>The screen read from inside a <c>WaitUntil</c> condition, which already runs on the UI thread.</summary>
    private static string[] LinesOnUi(Started s)
    {
        s.Host.App.LayoutAndDraw(true);
        return s.Host.App.Driver!.ToString()!.TrimEnd('\n').Split('\n');
    }

    private static bool ShowsOnUi(Started s, string text) => LinesOnUi(s).Any(l => l.Contains(text, StringComparison.Ordinal));

    private static int FileRowsOnUi(Started s) => LinesOnUi(s).Count(l => l.Contains(".ndpi", StringComparison.Ordinal));

    private static int FileRows(Started s) => s.Host.Lines.Count(l => l.Contains(".ndpi", StringComparison.Ordinal));

    private static void StartRun(Started s)
    {
        s.Host.Press((Key)'r');
        s.Host.WaitUntil(() => s.Vm.Files.Count > 0, "files in the list");
        s.Host.WaitUntil(() => FileRowsOnUi(s) > 0, "rows drawn");
    }

    [TestMethod, Timeout(60000)]
    public void L_shows_and_hides_the_pane_which_is_hidden_by_default()
    {
        var s = Start();
        Emit(s, "hello from the log");
        s.Host.WaitUntil(() => s.Log.Entries.Count == 1, "entry flushed");
        Assert.IsFalse(s.Page.ShowLog);
        Assert.IsFalse(s.Host.Shows("hello from the log"));

        s.Host.Press((Key)'l');
        s.Host.WaitUntilShows("hello from the log");
        Assert.IsTrue(s.Page.ShowLog);
        Assert.IsTrue(s.Host.Shows("INFO"), s.Host.Screen);

        s.Host.Press((Key)'l');
        s.Host.WaitUntil(() => !ShowsOnUi(s, "hello from the log"), "pane hidden");
    }

    [TestMethod, Timeout(60000)]
    public void At_80x24_the_table_keeps_9_rows_with_the_pane_open()
    {
        var s = Start();
        StartRun(s);
        Assert.AreEqual(17, FileRows(s), s.Host.Screen);

        s.Host.Press((Key)'l');
        s.Host.WaitUntil(() => FileRowsOnUi(s) == 9, "9 rows with the pane open");
        s.Host.Press((Key)'l');
        s.Host.WaitUntil(() => FileRowsOnUi(s) == 17, "17 rows again");
        s.Engine.Release();
    }

    [TestMethod, Timeout(60000)]
    public void Focus_and_follow_state_survive_toggling()
    {
        var s = Start();
        StartRun(s);
        s.Host.Press(Key.CursorDown);
        s.Host.WaitUntil(() => !s.Vm.IsFollowing, "manual move ends follow");

        s.Host.Press((Key)'l');
        s.Host.WaitUntil(() => s.Page.ShowLog, "open");
        s.Host.WaitUntil(() => s.Host.App.Navigation?.GetFocused() is TableView, "focus back on the table");
        Assert.IsFalse(s.Vm.IsFollowing);

        s.Host.Press((Key)'l');
        s.Host.WaitUntil(() => !s.Page.ShowLog, "closed");
        s.Host.WaitUntil(() => s.Host.App.Navigation?.GetFocused() is TableView, "focus on the table");
        Assert.IsFalse(s.Vm.IsFollowing);

        s.Host.Press(Key.End);
        s.Host.WaitUntil(() => s.Vm.IsFollowing, "End resumes following");
        s.Engine.Release();
    }

    [TestMethod, Timeout(60000)]
    public void The_pane_follows_the_newest_entry()
    {
        var s = Start();
        s.Host.Press((Key)'l');
        for (var i = 0; i < 50; i++) Emit(s, $"line-{i:D3}");
        s.Host.WaitUntilShows("line-049");
        Assert.IsFalse(s.Host.Shows("line-000"));
    }

    [TestMethod, Timeout(60000)]
    public void Five_thousand_appends_and_one_flush_take_under_two_seconds()
    {
        var s = Start();
        s.Host.Press((Key)'l');
        var clock = Stopwatch.StartNew();
        for (var i = 0; i < 5000; i++) Emit(s, $"entry-{i:D4}");
        s.Host.WaitUntilShows("entry-4999");
        clock.Stop();

        Assert.AreEqual(5000, s.Host.OnUi(() => s.Log.Entries.Count));
        Assert.IsLessThan(2000, clock.ElapsedMilliseconds, $"took {clock.ElapsedMilliseconds} ms");
    }
}

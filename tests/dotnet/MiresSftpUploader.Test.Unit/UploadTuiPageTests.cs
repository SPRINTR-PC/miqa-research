using System.Diagnostics;
using MiresSftpUploader.Core;
using MiresSftpUploader.SettingsTui;
using MiresSftpUploader.Test.Support;
using MiresSftpUploader.Tui;
using MiresSftpUploader.ViewModels;
using Terminal.Gui.Input;
using Terminal.Gui.Views;

namespace MiresSftpUploader.Test.Unit;

/// <summary>The Upload page of the whole-app TUI on the real view model, a gated fake Engine and the real <c>Application.Run</c> loop.</summary>
[TestClass]
[DoNotParallelize] // each test runs a TuiTestHost (own thread + Terminal.Gui loop); started alongside hundreds of other tests the loop starves and "the TUI did not start"
public sealed class UploadTuiPageTests : ConfigurationTestBase
{
    private static readonly AppConfig Config = new()
    {
        Sftp = new SftpConfig { Host = "sftp.mires.example", Port = 22 },
        Sources =
        [
            new SourceConfig { Name = "wsi", Path = "/data/wsi" },
            new SourceConfig { Name = "dicom", Path = "/data/dicom" },
        ],
    };

    private readonly List<TuiTestHost> _hosts = [];

    [TestCleanup]
    public void CloseHosts()
    {
        foreach (var h in _hosts) h.Dispose();
    }

    private sealed record Started(TuiTestHost Host, TuiShell Shell, UploadTuiPage Page, UploadPageViewModel Vm, FakeRunEngine Engine,
        FakeTuiDialogs Dialogs, SettingsPageViewModel Settings);

    private Started Start(IRunEngine? engine = null, int width = 100, int height = 32, AppConfig? config = null)
    {
        engine ??= new FakeRunEngine();
        var fake = engine as FakeRunEngine;
        var settings = new SettingsPageViewModel(Create(ValidMachine().ToJsonString()));
        var dialogs = new FakeTuiDialogs();
        TuiShell? shell = null;
        UploadTuiPage? page = null;
        UploadPageViewModel? vm = null;
        var host = new TuiTestHost(app =>
        {
            vm = new UploadPageViewModel(new FakeUploaderRuntime(config ?? Config, engine), a => app.Invoke(a), RunTrigger.Tui);
            page = new UploadTuiPage(app, vm, log: null, dialogs);
            shell = new TuiShell(app, settings, dialogs, ShellTab.Upload, page);
            shell.CancelWait = TimeSpan.FromSeconds(3);
            return shell;
        }, width, height);
        _hosts.Add(host);
        host.WaitUntil(() => shell!.IsInitialized, "shell initialised");
        host.WaitUntil(() => host.App.Navigation?.GetFocused() is TableView, "focus on the table");
        return new Started(host, shell!, page!, vm!, fake ?? new FakeRunEngine(), dialogs, settings);
    }

    private static FileOutcomeChanged File(string path, FileOutcome outcome, string source = "wsi", string? reason = null) =>
        new(source, path, outcome, reason);

    private static List<RunEvent> Files(int count, FileOutcome outcome = FileOutcome.Pending) =>
        Enumerable.Range(0, count).Select(i => (RunEvent)File($"f{i:D5}.ndpi", outcome)).ToList();

    /// <summary>The screen read from inside a <c>WaitUntil</c> condition, which already runs on the UI thread.</summary>
    private static string[] LinesOnUi(Started s)
    {
        s.Host.App.LayoutAndDraw(true);
        return s.Host.App.Driver!.ToString()!.TrimEnd('\n').Split('\n');
    }

    private static int FileRowsOnScreen(Started s) => s.Host.Lines.Count(l => l.Contains(".ndpi", StringComparison.Ordinal));

    private static void RunAndWaitForEvents(Started s, string key = "r")
    {
        s.Host.Press((Key)key[0]);
        s.Host.WaitUntil(() => s.Engine.Started.IsCompleted, "the Run reported its events");
        s.Host.WaitUntil(() => s.Vm.Files.Count > 0, "files in the list");
    }

    // ------------------------------------------------------------------ layout

    [TestMethod, Timeout(60000)]
    public void At_80x24_the_table_has_17_rows_and_the_left_column_shows_sources_filters_and_commands()
    {
        var engine = new FakeRunEngine { Hold = true };
        engine.Script.AddRange(Files(60));
        var s = Start(engine, 80, 24);

        RunAndWaitForEvents(s);
        s.Host.WaitUntil(() => LinesOnUi(s).Any(l => l.Contains(".ndpi")), "rows drawn");

        Assert.AreEqual(17, FileRowsOnScreen(s), s.Host.Screen);
        foreach (var text in new[] { "Sources", "[x] wsi", "[x] dicom", "✓ 0", "✗ 0", "⊘ 0", "… 60", "Run", "Dry run", "Scan", "Cancel", "Retry failed", "sftp.mires.example:22" })
            Assert.Contains(text, s.Host.Screen, text);
        Assert.IsLessThanOrEqualTo(80, s.Shell.KeyBarText.Length, s.Shell.KeyBarText);
        s.Engine.Release();
    }

    [TestMethod, Timeout(60000)]
    public void At_132x43_the_table_has_36_rows()
    {
        var engine = new FakeRunEngine { Hold = true };
        engine.Script.AddRange(Files(80));
        var s = Start(engine, 132, 43);

        RunAndWaitForEvents(s);
        s.Host.WaitUntil(() => LinesOnUi(s).Any(l => l.Contains(".ndpi")), "rows drawn");

        Assert.AreEqual(36, FileRowsOnScreen(s), s.Host.Screen);
        s.Engine.Release();
    }

    [TestMethod, Timeout(60000)]
    public void The_key_hints_fit_the_80_column_key_bar_in_every_state()
    {
        var engine = new FakeRunEngine { Hold = true };
        engine.Script.AddRange(Files(5));
        var s = Start(engine, 80, 24);
        void Check(string state) => Assert.IsLessThanOrEqualTo(80, s.Shell.KeyBarText.Length, $"{state}: {s.Shell.KeyBarText}");

        Check("idle");
        s.Host.OnUi(() => s.Vm.IsFollowing = false);
        s.Host.WaitUntil(() => s.Shell.KeyBarText.Contains("End Follow"), "End Follow hint");
        Check("idle, not following");
        RunAndWaitForEvents(s);
        s.Host.WaitUntil(() => s.Shell.KeyBarText.Contains("X Cancel"), "running hints");
        Check("running, not following");
        s.Engine.Release();
    }

    // ------------------------------------------------------------------ banner

    [TestMethod, Timeout(60000)]
    public void A_Data_Directory_problem_shows_Uploading_is_disabled_and_disables_the_Run_keys()
    {
        var s = Start();

        s.Host.OnUi(() => s.Vm.BlockedReason = "The Data Directory cannot be used");
        s.Host.WaitUntilShows("Uploading is disabled");
        s.Host.Press(Key.R);

        Assert.IsEmpty(s.Engine.Calls);
        Assert.IsFalse(s.Host.OnUi(() => ((System.Windows.Input.ICommand)s.Vm.StartCommand).CanExecute(null)));
    }

    [TestMethod, Timeout(60000)]
    public void Configuration_problems_and_no_included_Source_show_a_banner_and_block_the_Run_keys()
    {
        var s = Start(config: new AppConfig { Sources = [new SourceConfig { Name = "wsi", Path = "/data/wsi" }] });
        s.Host.OnUi(() => s.Vm.Sources[0].Included = false);
        s.Host.Press(Key.F10);
        s.Host.Press(Key.F9);
        s.Host.Press(Key.Space); // on the table, not the Sources list: nothing

        s.Host.OnUi(() => s.Page.RefreshAll());
        s.Host.WaitUntilShows("Include at least one Source");
        s.Host.Press(Key.R);

        Assert.IsEmpty(s.Engine.Calls);
    }

    // ------------------------------------------------------------------ follow

    [TestMethod, Timeout(60000)]
    public void Follow_mode_keeps_the_in_flight_row_visible_until_the_cursor_moves_and_End_follows_again()
    {
        var engine = new FakeRunEngine { Hold = true };
        engine.Script.AddRange(Files(60));
        engine.Script.Add(File("f00040.ndpi", FileOutcome.Uploading));
        var s = Start(engine, 80, 24);

        RunAndWaitForEvents(s);
        s.Host.WaitUntil(() => LinesOnUi(s).Any(l => l.Contains("f00040.ndpi")), "the in-flight row scrolled into view");
        Assert.IsTrue(s.Vm.IsFollowing);

        s.Host.Press(Key.CursorUp);
        Assert.IsFalse(s.Host.OnUi(() => s.Vm.IsFollowing), "a manual cursor move turns follow off");
        s.Host.WaitUntil(() => s.Shell.KeyBarText.Contains("End Follow"), "the key bar offers End Follow");

        s.Host.Press(Key.End);
        Assert.IsTrue(s.Host.OnUi(() => s.Vm.IsFollowing), "End turns it on");
        s.Host.WaitUntil(() => !s.Shell.KeyBarText.Contains("End Follow"), "the key bar stops offering End Follow");
        s.Engine.Release();
    }

    // ------------------------------------------------------------------ filters

    [TestMethod, Timeout(60000)]
    public void Filters_by_key_1_to_4_and_by_clicking_the_checkbox()
    {
        var engine = new FakeRunEngine { Hold = true };
        engine.Script.AddRange([File("a.ndpi", FileOutcome.Succeeded), File("b.ndpi", FileOutcome.Failed, reason: "reset"), File("c.ndpi", FileOutcome.Pending)]);
        var s = Start(engine);
        RunAndWaitForEvents(s);

        s.Host.Press(Key.D2);
        s.Host.WaitUntil(() => s.Vm.Filter == FileFilter.Failed, "failed filter by key");
        Assert.AreEqual(1, FileRowsOnScreen(s), s.Host.Screen);
        s.Host.Press(Key.D2);
        s.Host.WaitUntil(() => s.Vm.Filter == FileFilter.None, "filter off");

        var y = Array.FindIndex(s.Host.Lines, l => l.Contains("✓ 1", StringComparison.Ordinal));
        var x = s.Host.Lines[y].IndexOf("✓ 1", StringComparison.Ordinal);
        s.Host.Click(x, y);
        s.Host.WaitUntil(() => s.Vm.Filter == FileFilter.Succeeded, "succeeded filter by click");
        Assert.AreEqual(1, FileRowsOnScreen(s), s.Host.Screen);
        s.Host.Click(x, y);
        s.Host.WaitUntil(() => s.Vm.Filter == FileFilter.None, "filter off by click");
        s.Engine.Release();
    }

    // ------------------------------------------------------------------ Run lifecycle

    [TestMethod, Timeout(60000)]
    public void A_Run_from_start_to_finish_on_screen_with_the_badge_and_the_Tui_trigger()
    {
        var engine = new FakeRunEngine { Hold = true };
        engine.Script.AddRange([File("a.ndpi", FileOutcome.Succeeded), File("b.ndpi", FileOutcome.Pending)]);
        var s = Start(engine);

        Assert.DoesNotContain("▶", s.Host.Lines[0]);
        RunAndWaitForEvents(s);
        s.Host.WaitUntilShows("▶ Running…");
        s.Host.WaitUntil(() => LinesOnUi(s)[0].Contains("Upload ▶ 50%", StringComparison.Ordinal), "tab badge ▶ 50%");
        Assert.DoesNotContain("Settings changes apply", s.Shell.StatusText, "the note belongs to Settings only");
        s.Host.Press(Key.F11);
        s.Host.WaitUntil(() => s.Shell.StatusText.Contains("Settings changes apply to the next Run"), "the note on Settings during a Run");
        s.Host.Press(Key.F9);
        s.Host.WaitUntil(() => s.Shell.Current == ShellTab.Upload && !s.Shell.StatusText.Contains("Settings changes apply"), "the note gone on Upload");
        Assert.AreEqual(RunTrigger.Tui, s.Engine.Calls.Single().Trigger);

        s.Engine.Release();
        s.Host.WaitUntilShows("Run finished, exit code 0");
        Assert.DoesNotContain("▶", s.Host.Lines[0]);
        Assert.DoesNotContain("Settings changes apply", s.Shell.StatusText);
    }

    [TestMethod, Timeout(60000)]
    public void X_cancels_a_running_Run()
    {
        var engine = new FakeRunEngine { Hold = true };
        engine.Script.Add(File("a.ndpi", FileOutcome.Uploading));
        var s = Start(engine);
        RunAndWaitForEvents(s);

        s.Host.Press(Key.X);

        s.Host.WaitUntilShows("Cancelled");
        Assert.IsFalse(s.Host.OnUi(() => s.Vm.IsRunning));
    }

    [TestMethod, Timeout(60000)]
    public void Quit_during_a_Run_asks_and_Back_keeps_the_Run_going()
    {
        var engine = new FakeRunEngine { Hold = true };
        engine.Script.Add(File("a.ndpi", FileOutcome.Uploading));
        var s = Start(engine);
        RunAndWaitForEvents(s);

        s.Host.Press(Key.Q.WithCtrl);

        Assert.AreEqual(1, s.Dialogs.RunQuitAsked);
        Assert.IsFalse(s.Host.Stopped.IsSet);
        Assert.IsTrue(s.Host.OnUi(() => s.Vm.IsRunning));
        s.Engine.Release();
    }

    [TestMethod, Timeout(60000)]
    public void A_signal_while_the_quit_question_is_open_still_cancels_and_exits_130()
    {
        var engine = new FakeRunEngine { Hold = true };
        engine.Script.Add(File("a.ndpi", FileOutcome.Uploading));
        var s = Start(engine);
        s.Dialogs.OnAskCancelRunAndQuit = () => s.Shell.Terminate();
        RunAndWaitForEvents(s);

        s.Host.Press(Key.Q.WithCtrl);

        Assert.IsTrue(s.Host.Stopped.Wait(TimeSpan.FromSeconds(10)), "the TUI exits once the Run ended");
        Assert.AreEqual(ExitCodes.Cancelled, s.Shell.ExitCode);
        Assert.IsFalse(s.Vm.IsRunning);
    }

    [TestMethod, Timeout(60000)]
    public void Quit_during_a_Run_and_Cancel_the_Run_cancels_waits_and_exits_0()
    {
        var engine = new FakeRunEngine { Hold = true };
        engine.Script.Add(File("a.ndpi", FileOutcome.Uploading));
        var s = Start(engine);
        s.Dialogs.RunQuitAnswers.Enqueue(true);
        RunAndWaitForEvents(s);

        s.Host.Press(Key.Q.WithCtrl);

        Assert.IsTrue(s.Host.Stopped.Wait(TimeSpan.FromSeconds(10)), "the TUI exits once the Run ended");
        Assert.AreEqual(0, s.Shell.ExitCode);
        Assert.IsFalse(s.Vm.IsRunning);
        Assert.AreEqual("Cancelled", s.Vm.Status);
    }

    [TestMethod, Timeout(60000)]
    public void Quit_with_a_Run_and_unsaved_Settings_asks_about_the_Run_first_then_Settings()
    {
        var engine = new FakeRunEngine { Hold = true };
        engine.Script.Add(File("a.ndpi", FileOutcome.Uploading));
        var s = Start(engine);
        RunAndWaitForEvents(s);
        s.Host.OnUi(() => s.Settings.Field("Sftp:Port").Value = "2222");
        s.Dialogs.RunQuitAnswers.Enqueue(true);
        s.Dialogs.UnsavedAnswers.Enqueue(UnsavedChoice.Cancel);

        s.Host.Press(Key.Q.WithCtrl);

        Assert.AreEqual(1, s.Dialogs.RunQuitAsked);
        Assert.HasCount(1, s.Dialogs.UnsavedAsked);
        Assert.IsTrue(s.Host.OnUi(() => s.Vm.IsRunning), "Cancel on Settings leaves the Run alone");
        Assert.IsFalse(s.Host.Stopped.IsSet);

        s.Dialogs.RunQuitAnswers.Enqueue(true);
        s.Dialogs.UnsavedAnswers.Enqueue(UnsavedChoice.Discard);
        s.Host.Press(Key.Q.WithCtrl);
        Assert.IsTrue(s.Host.Stopped.Wait(TimeSpan.FromSeconds(10)));
        Assert.AreEqual(0, s.Shell.ExitCode);
    }

    [TestMethod, Timeout(60000)]
    public void A_signal_mid_Run_cancels_it_and_exits_130()
    {
        var engine = new FakeRunEngine { Hold = true };
        engine.Script.Add(File("a.ndpi", FileOutcome.Uploading));
        var s = Start(engine);
        RunAndWaitForEvents(s);

        s.Host.OnUi(() => s.Shell.Terminate());

        Assert.IsTrue(s.Host.Stopped.Wait(TimeSpan.FromSeconds(10)));
        Assert.AreEqual(ExitCodes.Cancelled, s.Shell.ExitCode);
        Assert.AreEqual("Cancelled", s.Vm.Status);
        Assert.AreEqual(0, s.Dialogs.RunQuitAsked);
    }

    [TestMethod, Timeout(60000)]
    public void A_second_signal_exits_at_once_even_if_the_Run_does_not_end()
    {
        // The Run ignores its token: only the second signal gets the TUI out within the wait.
        var engine = new StubbornEngine();
        var s = Start(engine);
        s.Shell.CancelWait = TimeSpan.FromSeconds(60);
        s.Host.Press(Key.R);
        s.Host.WaitUntil(() => engine.Entered.IsSet, "the Run started");

        s.Host.OnUi(() => s.Shell.Terminate());
        Assert.IsFalse(s.Host.Stopped.Wait(TimeSpan.FromMilliseconds(500)), "the first signal waits for the Run");
        s.Host.OnUi(() => s.Shell.Terminate());

        Assert.IsTrue(s.Host.Stopped.Wait(TimeSpan.FromSeconds(10)));
        Assert.AreEqual(ExitCodes.Cancelled, s.Shell.ExitCode);
        engine.Finish.Set();
    }

    [TestMethod, Timeout(60000)]
    public void A_Run_that_ignores_cancellation_is_left_after_the_wait_bound()
    {
        var engine = new StubbornEngine();
        var s = Start(engine);
        s.Shell.CancelWait = TimeSpan.FromMilliseconds(400);
        s.Dialogs.RunQuitAnswers.Enqueue(true);
        s.Host.Press(Key.R);
        s.Host.WaitUntil(() => engine.Entered.IsSet, "the Run started");

        s.Host.Press(Key.Q.WithCtrl);

        Assert.IsTrue(s.Host.Stopped.Wait(TimeSpan.FromSeconds(10)));
        Assert.AreEqual(0, s.Shell.ExitCode);
        engine.Finish.Set();
    }

    [TestMethod, Timeout(60000)]
    public void A_refused_Run_lock_shows_in_the_status_line_and_a_message_and_the_controls_stay_usable()
    {
        var engine = new FakeRunEngine { ExitCode = ExitCodes.LockHeld, Reason = "Another Run holds the lock (pid=7 user=ann since=today)" };
        var s = Start(engine);

        s.Host.Press(Key.R);

        s.Host.WaitUntil(() => s.Dialogs.Messages.Count == 1, "the dismissible message");
        StringAssert.Contains(s.Dialogs.Messages[0].Message, "pid=7 user=ann");
        s.Host.WaitUntilShows("Another Run holds the lock");
        engine.ExitCode = 0;
        engine.Reason = null;
        s.Host.Press(Key.R);
        s.Host.WaitUntilShows("Run finished, exit code 0");
        Assert.HasCount(2, engine.Calls);
    }

    // ------------------------------------------------------------------ scale

    [TestMethod, Timeout(120000)]
    public void Drawing_100k_rows_takes_under_a_second_without_copying_them()
    {
        // Events come from the Engine's own threads, in bursts, as in a real Run.
        var engine = new BurstEngine(Files(100_000).Append(File("f100000.ndpi", FileOutcome.Uploading)).ToList());
        var s = Start(engine, 80, 24);

        s.Host.Press(Key.R);
        s.Host.WaitUntil(() => s.Vm.Files.Count == 100_000 + 1, "100k rows", TimeSpan.FromSeconds(60));
        s.Host.WaitUntilShows("f100000.ndpi");
        var timer = Stopwatch.StartNew();
        s.Host.OnUi(() => s.Page.Table.SetNeedsDraw());
        _ = s.Host.Screen;
        timer.Stop();

        Assert.IsLessThan(1000, timer.ElapsedMilliseconds, "one frame of 100k rows");
        engine.Finish.Set();
    }

    /// <summary>An Engine that reports its events from a worker thread, then waits to be told to finish.</summary>
    private sealed class BurstEngine(List<RunEvent> events) : IRunEngine
    {
        public ManualResetEventSlim Finish { get; } = new();

        public async Task<RunResult> RunAsync(RunOptions options, IProgress<RunEvent> progress, CancellationToken cancellationToken)
        {
            var id = Guid.NewGuid();
            await Task.Run(() =>
            {
                progress.Report(new RunStarted(id, DateTimeOffset.UnixEpoch));
                foreach (var e in events) progress.Report(e);
                Finish.Wait(TimeSpan.FromSeconds(60));
            });
            return new RunResult(id, new Dictionary<FileOutcome, int>(), ExitCodes.Ok, null);
        }
    }

    /// <summary>An Engine that reports a started Run and then ignores its cancellation token until told to finish.</summary>
    private sealed class StubbornEngine : IRunEngine
    {
        public ManualResetEventSlim Entered { get; } = new();
        public ManualResetEventSlim Finish { get; } = new();

        public async Task<RunResult> RunAsync(RunOptions options, IProgress<RunEvent> progress, CancellationToken cancellationToken)
        {
            var id = Guid.NewGuid();
            progress.Report(new RunStarted(id, DateTimeOffset.UnixEpoch));
            Entered.Set();
            await Task.Run(() => Finish.Wait(TimeSpan.FromSeconds(30)));
            return new RunResult(id, new Dictionary<FileOutcome, int>(), ExitCodes.Cancelled, "Cancelled");
        }
    }
}

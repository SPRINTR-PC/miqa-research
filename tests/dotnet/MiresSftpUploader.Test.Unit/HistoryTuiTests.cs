using MiresSftpUploader.Core;
using MiresSftpUploader.SettingsTui;
using MiresSftpUploader.Test.Support;
using MiresSftpUploader.Tui;
using MiresSftpUploader.ViewModels;
using Terminal.Gui.Input;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
[DoNotParallelize] // each test runs a TuiTestHost (own thread + Terminal.Gui loop); started alongside hundreds of other tests the loop starves and "the TUI did not start"
public sealed class HistoryTuiTests : ConfigurationTestBase
{
    private readonly List<TuiTestHost> _hosts = [];
    private readonly FakeRunHistory _history = new();
    private readonly List<Guid> _retried = [];

    [TestCleanup]
    public void CloseHosts()
    {
        foreach (var h in _hosts) h.Dispose();
    }

    private sealed record Started(TuiTestHost Host, TuiShell Shell, HistoryTuiPage Page, HistoryPageViewModel Vm);

    private static Dictionary<string, int> Counts(int ok = 0, int failed = 0, int skipped = 0, int pending = 0) =>
        new[] { ("Succeeded", ok), ("Failed", failed), ("Skipped", skipped), ("Pending", pending) }
            .Where(c => c.Item2 > 0).ToDictionary(c => c.Item1, c => c.Item2);

    private static RunFileOutcome File(string path, string outcome, string? reason = null) => new("wsi", path, outcome, 100, 5, reason);

    private Started Start(int width = 100, int height = 32)
    {
        var settings = new SettingsPageViewModel(Create(ValidMachine().ToJsonString()));
        HistoryTuiPage? page = null;
        HistoryPageViewModel? vm = null;
        TuiShell? shell = null;
        TuiTestHost? host = null;
        host = new TuiTestHost(app =>
        {
            vm = new HistoryPageViewModel(_history, "anna", a => app.Invoke(a), id => { _retried.Add(id); return Task.CompletedTask; });
            page = new HistoryTuiPage(vm, a => app.Invoke(a));
            return shell = new TuiShell(app, settings, new FakeTuiDialogs(), ShellTab.History, history: page);
        }, width, height);
        _hosts.Add(host);
        host.WaitUntil(() => shell!.IsInitialized && shell.Current == ShellTab.History, "History shown");
        return new Started(host, shell!, page!, vm!);
    }

    private static void SeedMixed(FakeRunHistory h)
    {
        h.Add(status: "Running", exitCode: null, startedBy: "bo", counts: Counts(ok: 3, pending: 7), files: [File("live/a.svs", "Succeeded")]);
        h.Add(exitCode: 1, startedBy: "anna", counts: Counts(ok: 2, failed: 2), files:
            [File("a/ok1.svs", "Succeeded"), File("a/bad1.svs", "Failed", "Connection reset"), File("a/ok2.svs", "Succeeded"), File("a/bad2.svs", "Failed", "Checksum mismatch")]);
        h.Add(exitCode: 0, startedBy: "anna", counts: Counts(ok: 1), files: [File("b/fine.svs", "Succeeded")]);
    }

    [TestMethod, Timeout(60000)]
    public void The_list_shows_Runs_with_status_and_the_selected_Run_beside_it()
    {
        SeedMixed(_history);
        var s = Start();

        Assert.IsTrue(s.Host.Shows("Running"), s.Host.Screen);
        Assert.IsTrue(s.Host.Shows("Failed"), s.Host.Screen);
        Assert.IsTrue(s.Host.Shows("bo · Run"), s.Host.Screen);
        Assert.IsTrue(s.Host.Shows("●All"), s.Host.Screen);
        Assert.IsTrue(s.Host.Shows("3 Runs, 1 live, 1 need attention"), s.Host.Screen);
    }

    [TestMethod, Timeout(60000)]
    public void The_filter_keys_1_to_3_apply_while_the_table_has_the_focus()
    {
        SeedMixed(_history);
        var s = Start();

        s.Host.Press(Key.D3);
        s.Host.WaitUntil(() => s.Vm.Filter == RunFilterKind.Live, "Live filter");
        Assert.HasCount(1, s.Vm.Runs);
        s.Host.Press(Key.D2);
        s.Host.WaitUntil(() => s.Vm.Filter == RunFilterKind.NeedsAttention && s.Vm.Runs.Count == 1, "Attention filter");
        s.Host.Press(Key.D1);
        s.Host.WaitUntil(() => s.Vm.Filter == RunFilterKind.All && s.Vm.Runs.Count == 3, "All filter");
        StringAssert.Contains(s.Host.Lines.First(l => l.Contains("All")), "●All");
    }

    [TestMethod, Timeout(60000)]
    public void Clicking_a_filter_button_applies_it()
    {
        SeedMixed(_history);
        var s = Start();
        var line = s.Host.Lines.ToList().FindIndex(l => l.Contains("○Live"));
        Assert.IsGreaterThanOrEqualTo(0, line, s.Host.Screen);

        s.Host.Click(s.Host.Lines[line].IndexOf("○Live", StringComparison.Ordinal) + 2, line);

        s.Host.WaitUntil(() => s.Vm.Filter == RunFilterKind.Live, "Live filter by click");
    }

    [TestMethod, Timeout(60000)]
    public void Clicking_a_row_selects_that_Run()
    {
        SeedMixed(_history);
        var s = Start();
        var last = _history.ListRuns()[2];
        var lines = s.Host.Lines.ToList();
        var header = lines.FindIndex(l => l.Contains("Started"));
        Assert.IsGreaterThanOrEqualTo(0, header, s.Host.Screen);

        s.Host.Click(5, header + 4);

        s.Host.WaitUntil(() => s.Vm.Selected?.RunId == last.RunId, "third Run selected");
        Assert.IsTrue(s.Host.Shows("anna (you)"), s.Host.Screen);
    }

    [TestMethod, Timeout(60000)]
    public void The_selection_survives_a_refresh()
    {
        SeedMixed(_history);
        var s = Start();
        var second = _history.ListRuns()[1].RunId;
        s.Host.Press(Key.CursorDown);
        s.Host.WaitUntil(() => s.Vm.Selected?.RunId == second, "second Run selected");

        s.Host.Press(Key.F5);

        s.Host.WaitUntil(() => s.Vm.Selected?.RunId == second, "still selected after F5");
        Assert.AreEqual(second, s.Host.OnUi(() => s.Vm.Selected!.RunId));
    }

    [TestMethod, Timeout(60000)]
    public void A_Run_that_needs_attention_opens_with_Failed_only_on_and_F_toggles_it()
    {
        SeedMixed(_history);
        var s = Start();
        s.Host.Press(Key.CursorDown);

        s.Host.WaitUntil(() => s.Vm.Selected is { FailedOnly: true }, "failed only on by default");
        Assert.IsTrue(s.Host.Shows("bad1.svs"), s.Host.Screen);
        Assert.IsFalse(s.Host.Shows("ok1.svs"), s.Host.Screen);

        s.Host.Press(Key.F);
        s.Host.WaitUntil(() => s.Vm.Selected is { FailedOnly: false }, "failed only off");
        Assert.IsTrue(s.Host.Shows("ok1.svs"), s.Host.Screen);

        s.Host.Press(Key.F5);
        s.Host.Press(Key.F5);
        Assert.IsFalse(s.Host.OnUi(() => s.Vm.Selected!.FailedOnly), "the user's choice survives a refresh");
    }

    [TestMethod, Timeout(60000)]
    public void A_Run_without_failures_opens_with_every_outcome()
    {
        SeedMixed(_history);
        var s = Start();
        s.Host.Press(Key.CursorDown);
        s.Host.Press(Key.CursorDown);

        s.Host.WaitUntil(() => s.Vm.Selected?.Files.Count == 1, "third Run loaded");

        Assert.IsFalse(s.Vm.Selected!.FailedOnly);
        Assert.IsTrue(s.Host.Shows("fine.svs"), s.Host.Screen);
    }

    [TestMethod, Timeout(60000)]
    public void Another_users_live_Run_is_read_only_with_the_banner_and_Request_cancel()
    {
        SeedMixed(_history);
        var live = _history.ListRuns()[0].RunId;
        var s = Start();

        Assert.IsTrue(s.Host.Shows("Live view of bo's Run: read-only"), s.Host.Screen);
        Assert.IsTrue(s.Host.Shows("Request cancel"), s.Host.Screen);
    }

    [TestMethod, Timeout(60000)]
    public void X_requests_cancel_of_another_users_live_Run_and_the_banner_changes()
    {
        SeedMixed(_history);
        var live = _history.ListRuns()[0].RunId;
        var s = Start();

        s.Host.Press(Key.X);

        s.Host.WaitUntil(() => _history.CancelRequests.Contains(live), "cancel requested");
        s.Host.WaitUntilShows("Cancel requested of bo's Run.");
        s.Host.WaitUntilShows("Cancel requested:");
    }

    [TestMethod, Timeout(60000)]
    public void Live_updates_arrive_through_the_watch_and_redraw()
    {
        SeedMixed(_history);
        var live = _history.GetRun(_history.ListRuns()[0].RunId)!;
        var s = Start();
        Assert.IsTrue(s.Host.Shows("✓ 3 "), s.Host.Screen);

        _history.Publish(live with { Summary = live.Summary with { Counts = Counts(ok: 9, pending: 1) } });

        s.Host.WaitUntilShows("✓ 9 ");
    }

    [TestMethod, Timeout(60000)]
    public void J_and_C_export_a_Report_and_show_where_it_was_written()
    {
        SeedMixed(_history);
        var s = Start();

        s.Host.Press(Key.J);
        s.Host.WaitUntilShows(".json");
        s.Host.Press(Key.C);

        s.Host.WaitUntil(() => _history.Saved.Count == 2, "two exports");
        Assert.AreEqual(ReportFormat.Json, _history.Saved[0].Format);
        Assert.AreEqual(ReportFormat.Csv, _history.Saved[1].Format);
        Assert.IsTrue(s.Host.Shows(".csv"), "a long path keeps its end\n" + s.Host.Screen);
    }

    [TestMethod, Timeout(60000)]
    public void R_retries_a_finished_Run_with_failed_files_and_does_nothing_for_one_without()
    {
        SeedMixed(_history);
        var failed = _history.ListRuns()[1].RunId;
        var s = Start();

        s.Host.Press(Key.R);
        Assert.IsEmpty(_retried, "the first Run is live");
        s.Host.Press(Key.CursorDown);
        s.Host.WaitUntil(() => s.Vm.Selected?.RunId == failed, "failed Run selected");
        s.Host.Press(Key.R);

        s.Host.WaitUntil(() => _retried.Count == 1, "retry started");
        Assert.AreEqual(failed, _retried[0]);
    }

    [TestMethod, Timeout(60000)]
    public void Keys_1_to_3_and_R_work_only_on_the_History_page()
    {
        SeedMixed(_history);
        var s = Start();
        s.Host.Press(Key.F9);

        s.Host.Press(Key.D3);

        Assert.AreEqual(RunFilterKind.All, s.Host.OnUi(() => s.Vm.Filter));
    }

    [TestMethod, Timeout(60000)]
    public void The_layout_fits_at_80x24_with_8_outcome_rows()
    {
        var files = Enumerable.Range(0, 30).Select(i => File($"d/slide{i:D2}.svs", "Failed", "Permission denied")).ToList();
        _history.Add(exitCode: 1, counts: Counts(failed: 30), files: files);
        var s = Start(80, 24);
        var lines = s.Host.Lines;

        Assert.IsTrue(s.Host.Shows("●All") && s.Host.Shows("○Attention") && s.Host.Shows("○Live"), s.Host.Screen);
        Assert.IsTrue(s.Host.Shows("Failed only"), s.Host.Screen);
        Assert.IsTrue(s.Host.Shows("Cancel") && s.Host.Shows("Retry") && s.Host.Shows("JSON") && s.Host.Shows("CSV"), s.Host.Screen);
        Assert.IsTrue(s.Host.Shows("Outcomes (30)"), s.Host.Screen);
        Assert.AreEqual(8, lines.Count(l => l.Contains("slide")), s.Host.Screen);
        Assert.IsTrue(s.Host.Shows("1 Runs, 0 live, 1 need attention"), s.Host.Screen);
        Assert.IsTrue(s.Host.Shows("1-3 Filter"), s.Host.Screen);
    }

    [TestMethod, Timeout(60000)]
    public void The_layout_fits_at_132x43_with_more_outcome_rows()
    {
        var files = Enumerable.Range(0, 60).Select(i => File($"d/slide{i:D2}.svs", "Failed", "Permission denied")).ToList();
        _history.Add(exitCode: 1, counts: Counts(failed: 60), files: files);
        var s = Start(132, 43);

        Assert.AreEqual(27, s.Host.Lines.Count(l => l.Contains("slide")), s.Host.Screen);
        Assert.IsTrue(s.Host.Shows("Outcomes (60)"), s.Host.Screen);
    }
}

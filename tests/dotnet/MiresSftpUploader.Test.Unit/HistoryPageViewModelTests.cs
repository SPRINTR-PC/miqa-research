using System.Reactive.Linq;
using System.Reactive.Threading.Tasks;
using System.Windows.Input;
using MiresSftpUploader.Core;
using MiresSftpUploader.Test.Support;
using MiresSftpUploader.ViewModels;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class HistoryPageViewModelTests
{
    private readonly FakeRunHistory _history = new();
    private readonly List<Guid> _retried = [];

    private HistoryPageViewModel NewPage(string user = "anna") =>
        new(_history, user, a => a(), id => { _retried.Add(id); return Task.FromResult<string?>(null); });

    private static Dictionary<string, int> Counts(int ok = 0, int failed = 0, int skipped = 0, int pending = 0, int movedAway = 0) =>
        new[] { ("Succeeded", ok), ("Failed", failed), ("Skipped", skipped), ("Pending", pending), ("MovedAway", movedAway) }
            .Where(c => c.Item2 > 0).ToDictionary(c => c.Item1, c => c.Item2);

    private static RunFileOutcome File(string path, string outcome, string? reason = null, string source = "wsi") =>
        new(source, path, outcome, 100, 5, reason);

    private static bool Can(ICommand command) => command.CanExecute(null);

    private static async Task Eventually(Func<bool> condition)
    {
        var deadline = DateTime.UtcNow.AddSeconds(5);
        while (!condition())
        {
            if (DateTime.UtcNow > deadline) Assert.Fail("The condition did not become true.");
            await Task.Delay(10);
        }
    }

    [TestMethod]
    public void The_list_shows_each_Run_with_status_who_mode_counts_and_time_newest_first()
    {
        var finished = _history.Add(exitCode: 1, startedBy: "bo", mode: "Run", counts: Counts(ok: 7, failed: 2, skipped: 3));
        var dry = _history.Add(startedBy: "anna", mode: "DryRun", counts: Counts(skipped: 4));

        var page = NewPage();

        CollectionAssert.AreEqual(new[] { finished.Summary.RunId, dry.Summary.RunId }, page.Runs.Select(r => r.RunId).ToArray());
        var first = page.Runs[0];
        Assert.AreEqual("Failed", first.StatusText);
        Assert.AreEqual("bo", first.StartedBy);
        Assert.AreEqual("Run", first.ModeText);
        Assert.AreEqual("7 succeeded · 2 failed · 3 skipped", first.CountsText);
        Assert.AreEqual("Dry run", page.Runs[1].ModeText);
        Assert.AreEqual(finished.Summary.RunId.ToString("N")[..8], first.ShortId);
    }

    [TestMethod]
    public void Status_covers_Running_Abandoned_Cancelled_Succeeded_and_Failed()
    {
        _history.Add(status: "Running", exitCode: null);
        _history.Add(status: "Abandoned", exitCode: null);
        _history.Add(exitCode: ExitCodes.Cancelled);
        _history.Add(exitCode: 0);
        _history.Add(exitCode: ExitCodes.SomeFilesFailed);

        var page = NewPage();

        CollectionAssert.AreEqual(new[] { "Running", "Abandoned", "Cancelled", "Succeeded", "Failed" }, page.Runs.Select(r => r.StatusText).ToArray());
        CollectionAssert.AreEqual(new[] { false, true, false, false, true }, page.Runs.Select(r => r.NeedsAttention).ToArray());
    }

    [TestMethod]
    public void A_live_Run_shows_progress_from_its_counts()
    {
        _history.Add(status: "Running", exitCode: null, counts: Counts(ok: 3, failed: 1, pending: 4));

        var run = NewPage().Runs.Single();

        Assert.AreEqual(50.0, run.Progress);
        Assert.AreEqual("4 of 8 files", run.ProgressText);
    }

    [TestMethod]
    public void The_filters_ask_the_Run_History_for_All_Needs_attention_and_Live()
    {
        _history.Add(exitCode: 0);
        _history.Add(exitCode: 1);
        _history.Add(status: "Running", exitCode: null);
        var page = NewPage();
        Assert.HasCount(3, page.Runs);

        page.Filter = RunFilterKind.NeedsAttention;
        Assert.HasCount(1, page.Runs);
        Assert.AreEqual(RunFilterKind.NeedsAttention, _history.Filters.Last().Kind);

        page.FilterIndex = 2;
        Assert.AreEqual(RunFilterKind.Live, page.Filter);
        Assert.AreEqual("Running", page.Runs.Single().StatusText);
        CollectionAssert.AreEqual(new[] { "All", "Needs attention", "Live now" }, HistoryPageViewModel.FilterNames.ToArray());
    }

    [TestMethod]
    public void Selecting_a_Run_shows_header_counts_with_Too_Recent_and_Moved_away_and_its_outcomes()
    {
        var run = _history.Add(exitCode: 1, startedBy: "bo", counts: Counts(ok: 1, failed: 1, skipped: 2, movedAway: 1), files:
        [
            File("a", "Succeeded"), File("b", "Failed", "RemoteDenied"), File("c", "Skipped", "TooRecent"),
            File("d", "Skipped", "Unchanged"), File("e", "MovedAway"),
        ]);
        var page = NewPage();

        page.Selected = page.Runs.Single();

        var detail = page.Selected!;
        Assert.AreEqual(run.Summary.RunId, detail.RunId);
        Assert.AreEqual("Exit code 1", detail.ExitText);
        Assert.AreEqual("3 min 0 s", detail.DurationText);
        Assert.AreEqual(2, detail.Skipped);
        Assert.AreEqual(1, detail.TooRecent);
        Assert.AreEqual(1, detail.MovedAway);
        Assert.HasCount(5, detail.VisibleFiles);
        Assert.AreEqual("Moved away", detail.VisibleFiles[4].OutcomeText);
        Assert.AreEqual("Too Recent", detail.VisibleFiles[2].ReasonText);

        detail.FailedOnly = true;
        CollectionAssert.AreEqual(new[] { "b" }, detail.VisibleFiles.Select(f => f.Path).ToArray());
    }

    [TestMethod]
    public void Expanding_a_Run_in_the_list_loads_its_outcomes_inline()
    {
        _history.Add(files: [File("a", "Succeeded")]);
        var page = NewPage();
        Assert.IsEmpty(page.Runs[0].VisibleFiles);

        page.Runs[0].IsExpanded = true;

        Assert.HasCount(1, page.Runs[0].VisibleFiles);
        Assert.IsNull(page.Selected, "expanding does not change the selection");
    }

    [TestMethod]
    public void Refresh_keeps_the_selection_and_the_expanded_Runs()
    {
        var run = _history.Add(files: [File("a", "Succeeded")]);
        _history.Add();
        var page = NewPage();
        page.Selected = page.Runs[0];
        page.Runs[1].IsExpanded = true;

        page.RefreshCommand.Execute().Subscribe();

        Assert.AreEqual(run.Summary.RunId, page.Selected!.RunId);
        Assert.IsTrue(page.Runs[1].IsExpanded);
        Assert.HasCount(1, page.Selected.VisibleFiles);
        Assert.IsGreaterThanOrEqualTo(2, _history.SweepCount, "stale heartbeats are swept before listing");
    }

    [TestMethod]
    public void Cancel_on_an_own_live_Run_requests_the_cancel_and_Request_cancel_on_anothers_says_whose_Run_it_is()
    {
        var own = _history.Add(status: "Running", exitCode: null, startedBy: "anna");
        var other = _history.Add(status: "Running", exitCode: null, startedBy: "sofia");
        var page = NewPage("Anna");
        var mine = page.Runs[0];
        var theirs = page.Runs[1];

        Assert.IsTrue(mine.IsOwn);
        Assert.AreEqual("Cancel", mine.CancelLabel);
        Assert.AreEqual("Request cancel (sofia's Run)", theirs.CancelLabel);
        Assert.IsTrue(theirs.IsLiveOthers);
        Assert.IsFalse(mine.IsLiveOthers);
        Assert.IsTrue(Can(mine.CancelCommand));
        Assert.IsTrue(Can(theirs.CancelCommand));

        theirs.CancelCommand.Execute().Subscribe();

        CollectionAssert.AreEqual(new[] { other.Summary.RunId }, _history.CancelRequests);
        Assert.IsTrue(theirs.ShowCancelRequested, "the pending banner");
        Assert.IsFalse(Can(theirs.CancelCommand), "asking twice is pointless");
        Assert.IsFalse(mine.ShowCancelRequested);
        Assert.IsTrue(Can(mine.CancelCommand));
        Assert.AreEqual("Cancel requested of sofia's Run.", page.Notice);

        mine.CancelCommand.Execute().Subscribe();
        CollectionAssert.AreEqual(new[] { other.Summary.RunId, own.Summary.RunId }, _history.CancelRequests);
        Assert.AreEqual("Cancel requested.", page.Notice);
    }

    [TestMethod]
    public void Cancel_is_not_available_for_a_Run_that_is_not_live()
    {
        _history.Add(exitCode: 1, counts: Counts(failed: 1));

        var run = NewPage().Runs.Single();

        Assert.IsFalse(Can(run.CancelCommand));
        Assert.IsFalse(run.ShowCancelRequested);
    }

    [TestMethod]
    public void Cancel_of_a_Run_that_ended_meanwhile_says_so()
    {
        var run = _history.Add(status: "Running", exitCode: null);
        var page = NewPage();
        _history.Replace(run with { Summary = run.Summary with { Status = "Finished", ExitCode = 0 } });

        page.Runs[0].CancelCommand.Execute().Subscribe();

        Assert.AreEqual("The Run has already ended.", page.Notice);
        Assert.IsFalse(page.Runs[0].IsLive);
    }

    [TestMethod]
    public void Retry_is_available_for_a_finished_Run_with_failures_and_for_an_Abandoned_Run_and_starts_a_Retry_of_it()
    {
        var failed = _history.Add(exitCode: 1, counts: Counts(ok: 1, failed: 1));
        _history.Add(exitCode: 0, counts: Counts(ok: 2));
        _history.Add(status: "Running", exitCode: null, counts: Counts(failed: 1));
        var abandoned = _history.Add(status: "Abandoned", exitCode: null, counts: Counts(failed: 1), startedBy: "sofia");
        var page = NewPage();

        CollectionAssert.AreEqual(new[] { true, false, false, true }, page.Runs.Select(r => Can(r.RetryCommand)).ToArray());

        page.Runs[0].RetryCommand.Execute().Subscribe();
        page.Runs[3].RetryCommand.Execute().Subscribe();

        CollectionAssert.AreEqual(new[] { failed.Summary.RunId, abandoned.Summary.RunId }, _retried);
    }

    [TestMethod]
    public void Export_writes_the_Report_and_says_where()
    {
        var run = _history.Add();
        var page = NewPage();

        page.Runs[0].ExportJsonCommand.Execute().Subscribe();
        Assert.AreEqual($"Report written: /reports/run-{run.Summary.RunId}.json", page.Notice);
        page.Runs[0].ExportCsvCommand.Execute().Subscribe();
        Assert.AreEqual($"Report written: /reports/run-{run.Summary.RunId}.csv", page.Notice);
        CollectionAssert.AreEqual(new[] { ReportFormat.Json, ReportFormat.Csv }, _history.Saved.Select(s => s.Format).ToArray());
    }

    [TestMethod]
    public async Task A_live_Run_is_followed_until_it_ends_and_an_Abandoned_one_shows_the_banner_state()
    {
        var run = _history.Add(status: "Running", exitCode: null, startedBy: "sofia", counts: Counts(ok: 1, pending: 3));
        var page = NewPage();
        page.Selected = page.Runs[0];
        var item = page.Runs[0];

        _history.Publish(run with
        {
            Summary = run.Summary with { Counts = Counts(ok: 4), Heartbeat = run.Summary.Heartbeat.AddSeconds(30) },
            Files = [File("a", "Succeeded")],
        });
        await Eventually(() => item.Succeeded == 4);
        Assert.AreEqual(100.0, item.Progress);
        Assert.HasCount(1, item.VisibleFiles);

        _history.Publish(run with { Summary = run.Summary with { Status = "Abandoned", ExitCode = null, EndedAt = run.Summary.Heartbeat } }, complete: true);
        await Eventually(() => item.IsAbandoned);
        Assert.IsFalse(item.IsLive);
        Assert.IsTrue(Can(item.RetryCommand));
        Assert.IsFalse(Can(item.CancelCommand));
    }
}

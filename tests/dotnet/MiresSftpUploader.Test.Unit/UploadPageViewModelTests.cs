using System.Reactive.Linq;
using System.Reactive.Threading.Tasks;
using System.Windows.Input;
using MiresSftpUploader.Core;
using MiresSftpUploader.Test.Support;
using MiresSftpUploader.ViewModels;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class UploadPageViewModelTests
{
    private static readonly AppConfig Config = new()
    {
        Sftp = new SftpConfig { Host = "sftp.mires.example", Port = 22 },
        Sources =
        [
            new SourceConfig { Name = "wsi", Path = "/data/wsi" },
            new SourceConfig { Name = "dicom", Type = SourceType.S3, Bucket = "mires", Prefix = "export/" },
            new SourceConfig { Name = "off", Path = "/data/off", Enabled = false },
        ],
    };

    private readonly FakeRunEngine _engine = new();

    private UploadPageViewModel NewPage(AppConfig? config = null, IReadOnlyList<ConfigError>? errors = null, bool noEngine = false) =>
        new(new FakeUploaderRuntime(config ?? Config, noEngine ? null : _engine, errors), post: a => a());

    private static FileOutcomeChanged File(string path, FileOutcome outcome, string source = "wsi", string? reason = null) =>
        new(source, path, outcome, reason);

    private static bool Can(ICommand command) => command.CanExecute(null);

    private static Task Start(UploadPageViewModel page) => page.StartCommand.Execute().ToTask();

    [TestMethod]
    public void The_sidebar_lists_the_enabled_Sources_with_summaries_and_the_Destination()
    {
        var page = NewPage();

        CollectionAssert.AreEqual(new[] { "wsi", "dicom" }, page.Sources.Select(s => s.Name).ToArray());
        CollectionAssert.AreEqual(new[] { "Directory · /data/wsi", "S3 · mires/export/" }, page.Sources.Select(s => s.Summary).ToArray());
        Assert.IsTrue(page.Sources.All(s => s.Included));
        Assert.AreEqual("sftp.mires.example:22", page.Destination);
    }

    [TestMethod]
    public async Task Start_runs_the_included_Sources_as_a_Run_started_from_the_UI()
    {
        var page = NewPage();
        page.Sources[1].Included = false;

        await Start(page);

        var options = _engine.Calls.Single();
        CollectionAssert.AreEqual(new[] { "wsi" }, options.SourceNames.ToArray());
        Assert.IsFalse(options.DryRun);
        Assert.AreEqual(RunTrigger.Ui, options.Trigger);
        Assert.IsNull(options.RetryOf);
    }

    [TestMethod]
    public async Task Dry_run_and_Scan_are_Dry_Runs_that_list_the_planned_files()
    {
        _engine.Script.Add(File("a.ndpi", FileOutcome.Pending));
        var page = NewPage();

        await page.DryRunCommand.Execute().ToTask();
        await page.ScanCommand.Execute().ToTask();

        Assert.IsTrue(_engine.Calls.All(c => c.DryRun));
        Assert.HasCount(2, _engine.Calls);
        Assert.AreEqual(1, page.Files.Count);
        Assert.AreEqual(1, page.Pending);
    }

    [TestMethod]
    public async Task A_Dry_Run_shows_each_planned_zip_as_a_row_that_is_not_counted_as_a_file()
    {
        _engine.Script.Add(File("d/a.dcm", FileOutcome.Pending, reason: "Would be packed into d/dicom-d.zip (rule dicom)"));
        _engine.Script.Add(new ArchivePlanned("wsi", "d/dicom-d.zip", "dicom", 1, 2048, 2048, "WouldBuild"));
        var page = NewPage();

        await page.DryRunCommand.Execute().ToTask();

        Assert.AreEqual(2, page.Files.Count);
        var zip = page.Files.Single(f => f.Path == "d/dicom-d.zip");
        StringAssert.Contains(zip.Reason, "rule dicom");
        StringAssert.Contains(zip.Reason, "1 files, 2 KiB");
        StringAssert.Contains(zip.Reason, "Would be built");
        Assert.AreEqual(1, page.Pending);
    }

    [TestMethod]
    public async Task Tiles_and_overall_progress_follow_the_File_Outcomes()
    {
        _engine.Script.AddRange(
        [
            File("a", FileOutcome.Pending), File("b", FileOutcome.Pending), File("c", FileOutcome.Pending), File("d", FileOutcome.Pending), File("e", FileOutcome.Pending),
            File("a", FileOutcome.Succeeded), File("b", FileOutcome.Failed, reason: "connection reset"),
            File("c", FileOutcome.Skipped, reason: "unchanged"), File("d", FileOutcome.Ignored, reason: "built-in"),
            File("e", FileOutcome.Uploading),
        ]);
        var page = NewPage();

        await Start(page);

        Assert.AreEqual(1, page.Succeeded);
        Assert.AreEqual(1, page.Failed);
        Assert.AreEqual(1, page.Skipped);
        Assert.AreEqual(1, page.Pending, "a file still uploading is pending");
        Assert.AreEqual(75.0, page.OverallProgress, "three of the four files that were not Ignored are done");
        Assert.AreEqual(5, page.Files.Count);
    }

    [TestMethod]
    public async Task Status_reports_the_exit_code_of_the_finished_Run()
    {
        _engine.ExitCode = ExitCodes.SomeFilesFailed;
        var page = NewPage();

        await Start(page);

        StringAssert.Contains(page.Status, "exit code 1");
        Assert.IsFalse(page.IsRunning);
    }

    [TestMethod]
    public async Task A_filter_shows_just_the_matching_files_and_clicking_it_again_clears_it()
    {
        _engine.Script.AddRange([File("a", FileOutcome.Succeeded), File("b", FileOutcome.Failed, reason: "x"), File("c", FileOutcome.Succeeded), File("d", FileOutcome.Skipped, reason: "same")]);
        var page = NewPage();
        await Start(page);

        page.FilterFailed = true;
        CollectionAssert.AreEqual(new[] { "b" }, page.Files.Select(f => f.Path).ToArray());

        page.FilterFailed = false;
        CollectionAssert.AreEqual(new[] { "a", "b", "c", "d" }, page.Files.Select(f => f.Path).ToArray());
    }

    [TestMethod]
    public async Task Several_filters_can_be_active_at_once_and_each_is_cleared_on_its_own()
    {
        _engine.Script.AddRange([File("a", FileOutcome.Succeeded), File("b", FileOutcome.Failed, reason: "x"), File("d", FileOutcome.Skipped, reason: "same")]);
        var page = NewPage();
        await Start(page);

        page.FilterFailed = true;
        page.FilterSkipped = true;
        Assert.IsTrue(page.FilterFailed);
        CollectionAssert.AreEqual(new[] { "b", "d" }, page.Files.Select(f => f.Path).ToArray());

        page.FilterFailed = false;
        Assert.IsTrue(page.FilterSkipped);
        CollectionAssert.AreEqual(new[] { "d" }, page.Files.Select(f => f.Path).ToArray());

        page.FilterSkipped = false;
        CollectionAssert.AreEqual(new[] { "a", "b", "d" }, page.Files.Select(f => f.Path).ToArray());
    }

    [TestMethod]
    public async Task Cancel_and_Retry_are_enabled_only_when_they_apply()
    {
        _engine.Hold = true;
        _engine.Script.Add(File("a", FileOutcome.Failed, reason: "x"));
        _engine.ExitCode = ExitCodes.SomeFilesFailed;
        var page = NewPage();

        Assert.IsTrue(Can(page.StartCommand));
        Assert.IsFalse(Can(page.CancelCommand), "nothing to cancel while idle");
        Assert.IsFalse(Can(page.RetryFailedCommand), "nothing to retry yet");

        var running = Start(page);
        await _engine.Started;
        Assert.IsFalse(Can(page.StartCommand), "one Run at a time");
        Assert.IsFalse(Can(page.DryRunCommand));
        Assert.IsFalse(Can(page.ScanCommand));
        Assert.IsTrue(Can(page.CancelCommand));
        Assert.IsFalse(Can(page.RetryFailedCommand));

        _engine.Release();
        await running;
        Assert.IsTrue(Can(page.StartCommand));
        Assert.IsFalse(Can(page.CancelCommand));
        Assert.IsTrue(Can(page.RetryFailedCommand), "a finished Run with failures can be retried");
    }

    [TestMethod]
    public async Task Retrying_a_Run_from_the_History_uploads_its_failed_files_again_as_a_new_Run_with_a_fresh_list()
    {
        var page = NewPage();
        _engine.Script.Add(File("old", FileOutcome.Failed));
        await Start(page);
        _engine.Script.Clear();
        _engine.Script.Add(File("new", FileOutcome.Succeeded));
        var earlier = Guid.NewGuid();

        await page.RetryRunAsync(earlier);

        Assert.AreEqual(earlier, _engine.Calls[1].RetryOf);
        Assert.AreEqual(RunTrigger.Ui, _engine.Calls[1].Trigger);
        CollectionAssert.AreEqual(new[] { "new" }, page.Files.Select(f => f.Path).ToArray());
    }

    [TestMethod]
    public async Task Retry_failed_runs_again_the_failed_files_of_the_last_Run_without_clearing_the_list()
    {
        _engine.Script.AddRange([File("a", FileOutcome.Succeeded), File("b", FileOutcome.Failed, reason: "x")]);
        _engine.ExitCode = ExitCodes.SomeFilesFailed;
        var page = NewPage();
        await Start(page);
        var firstRun = _engine.LastRunId;

        _engine.Script.Clear();
        _engine.Script.Add(File("b", FileOutcome.Succeeded));
        _engine.ExitCode = ExitCodes.Ok;
        await page.RetryFailedCommand.Execute().ToTask();

        Assert.AreEqual(firstRun, _engine.Calls[1].RetryOf);
        Assert.AreEqual(2, page.Succeeded);
        Assert.AreEqual(0, page.Failed);
        Assert.IsFalse(Can(page.RetryFailedCommand), "nothing failed any more");
    }

    [TestMethod]
    public async Task Cancel_stops_the_Run_and_the_status_says_so()
    {
        _engine.Hold = true;
        var page = NewPage();
        var running = Start(page);
        await _engine.Started;

        page.CancelCommand.Execute().Subscribe();
        await running;

        StringAssert.Contains(page.Status, "Cancelled");
        Assert.IsFalse(page.IsRunning);
    }

    [TestMethod]
    public async Task A_configuration_with_errors_starts_nothing_and_lists_the_problems()
    {
        var page = NewPage(config: null, errors: [new ConfigError("Sftp:Host", "is required.")], noEngine: true);

        await Start(page);

        Assert.IsEmpty(_engine.Calls);
        StringAssert.Contains(page.Status, "1 error");
        StringAssert.Contains(page.Problems, "Sftp:Host");
    }

    [TestMethod]
    public async Task Start_with_no_Source_included_starts_nothing()
    {
        var page = NewPage();
        foreach (var source in page.Sources) source.Included = false;

        await Start(page);

        Assert.IsEmpty(_engine.Calls);
        StringAssert.Contains(page.Status, "Include at least one Source");
    }

    [TestMethod]
    public async Task An_unexpected_failure_of_the_Engine_ends_the_Run_with_a_message_instead_of_crashing()
    {
        _engine.Throw = new InvalidOperationException("boom");
        var page = NewPage();

        await Start(page);

        StringAssert.Contains(page.Status, "boom");
        Assert.IsFalse(page.IsRunning);
        Assert.IsTrue(Can(page.StartCommand));
    }

    [TestMethod]
    public async Task A_new_Run_clears_the_list_of_the_previous_one()
    {
        _engine.Script.Add(File("a", FileOutcome.Succeeded));
        var page = NewPage();
        await Start(page);

        _engine.Script.Clear();
        _engine.Script.Add(File("z", FileOutcome.Succeeded));
        await Start(page);

        CollectionAssert.AreEqual(new[] { "z" }, page.Files.Select(f => f.Path).ToArray());
        Assert.AreEqual(1, page.Succeeded);
    }

    [TestMethod]
    public void A_blocked_page_cannot_start_a_Run_until_it_is_unblocked()
    {
        var page = NewPage();
        Assert.IsTrue(Can(page.StartCommand));

        page.BlockedReason = "The Data Directory '/srv/mires' is not writable by account 'alice'.";

        Assert.IsTrue(page.IsBlocked);
        Assert.IsFalse(Can(page.StartCommand));
        Assert.IsFalse(Can(page.DryRunCommand));
        Assert.IsFalse(Can(page.ScanCommand));

        page.BlockedReason = "";

        Assert.IsFalse(page.IsBlocked);
        Assert.IsTrue(Can(page.StartCommand));
    }

    [TestMethod]
    public void The_trigger_of_the_Runs_is_the_one_given_to_the_page()
    {
        var page = new UploadPageViewModel(new FakeUploaderRuntime(Config, _engine), a => a(), RunTrigger.Tui);

        Start(page).GetAwaiter().GetResult();

        Assert.AreEqual(RunTrigger.Tui, _engine.Calls.Single().Trigger);
    }

    [TestMethod]
    public async Task Follow_target_is_the_first_in_flight_row_else_the_first_Pending_else_the_last()
    {
        _engine.Script.AddRange([File("a", FileOutcome.Succeeded), File("b", FileOutcome.Pending), File("c", FileOutcome.Pending), File("d", FileOutcome.Uploading)]);
        var page = NewPage();

        await Start(page);
        Assert.AreEqual(3, page.FollowIndex, "the file being uploaded");

        _engine.Script.Clear();
        _engine.Script.AddRange([File("a", FileOutcome.Succeeded), File("b", FileOutcome.Pending), File("c", FileOutcome.Pending)]);
        await Start(page);
        Assert.AreEqual(1, page.FollowIndex, "the first file still waiting");

        _engine.Script.Clear();
        _engine.Script.AddRange([File("a", FileOutcome.Succeeded), File("b", FileOutcome.Failed)]);
        await Start(page);
        Assert.AreEqual(1, page.FollowIndex, "the last row");
    }

    [TestMethod]
    public void Follow_target_is_minus_one_without_files_and_following_is_on_until_turned_off()
    {
        var page = NewPage();

        Assert.IsTrue(page.IsFollowing);
        Assert.AreEqual(-1, page.FollowIndex);
        page.IsFollowing = false;
        Assert.IsFalse(page.IsFollowing);
    }

    [TestMethod]
    public async Task A_refused_Run_lock_is_reported_as_a_notice_and_cleared_by_the_next_Run()
    {
        _engine.ExitCode = ExitCodes.LockHeld;
        _engine.Reason = "Another Run holds the lock (pid=7 user=ann since=now)";
        var page = NewPage();

        await Start(page);
        Assert.AreEqual("Another Run holds the lock (pid=7 user=ann since=now)", page.LockRefusal);

        _engine.ExitCode = 0;
        _engine.Reason = null;
        await Start(page);
        Assert.AreEqual("", page.LockRefusal);
    }

    private const long MiB = 1L << 20;

    private static UploadProgress Snapshot(double? total, params UploadingFile[] files) => new(files, total);

    private static UploadingFile Uploading(string path, long sent, long size, double? speed, string source = "wsi") =>
        new(source, path, sent, size, speed);

    /// <summary>Starts a Run that holds after its scripted events, so the page can be inspected while it "uploads".</summary>
    private async Task<Task> StartHeld(UploadPageViewModel page)
    {
        _engine.Hold = true;
        var run = Start(page);
        await _engine.Started;
        return run;
    }

    [TestMethod]
    public async Task A_snapshot_fills_the_Uploading_now_card_with_bar_percent_speed_and_the_total()
    {
        _engine.Script.Add(File("a.ndpi", FileOutcome.Uploading));
        _engine.Script.Add(File("b.ndpi", FileOutcome.Uploading));
        _engine.Script.Add(Snapshot(9.2 * MiB, Uploading("a.ndpi", 42 * MiB, 100 * MiB, 3.1 * MiB), Uploading("b.ndpi", 61 * MiB, 100 * MiB, 6.1 * MiB)));
        var page = NewPage();

        var run = await StartHeld(page);

        Assert.IsTrue(page.HasActiveUploads);
        CollectionAssert.AreEqual(new[] { "a.ndpi", "b.ndpi" }, page.ActiveUploads.Select(u => u.Path).ToArray());
        var a = page.ActiveUploads[0];
        Assert.IsTrue(a.HasProgress);
        Assert.AreEqual(42, a.Percent, 0.001);
        Assert.AreEqual("42%", a.PercentText);
        Assert.AreEqual("3.1 MiB/s", a.SpeedText);
        Assert.AreEqual("9.2 MiB/s", page.TotalUploadSpeedText);
        Assert.IsTrue(page.HasTotalUploadSpeed);
        Assert.AreEqual(42 * MiB, page.Files[0].Progress!.BytesSent);
        _engine.Release();
        await run;
    }

    [TestMethod]
    public async Task A_file_without_an_Upload_Speed_yet_shows_no_bar_or_speed_and_the_total_stays_empty()
    {
        _engine.Script.Add(File("a.ndpi", FileOutcome.Uploading));
        _engine.Script.Add(Snapshot(null, Uploading("a.ndpi", 5 * MiB, 100 * MiB, null)));
        var page = NewPage();

        var run = await StartHeld(page);

        Assert.AreEqual(1, page.ActiveUploads.Count);
        Assert.IsFalse(page.ActiveUploads[0].HasProgress);
        Assert.AreEqual("", page.ActiveUploads[0].SpeedText);
        Assert.IsFalse(page.HasTotalUploadSpeed);
        _engine.Release();
        await run;
    }

    [TestMethod]
    public async Task The_card_is_hidden_after_the_last_empty_snapshot_and_the_row_bar_is_gone()
    {
        _engine.Script.Add(File("a.ndpi", FileOutcome.Uploading));
        _engine.Script.Add(Snapshot(3 * MiB, Uploading("a.ndpi", MiB, 100 * MiB, 3 * MiB)));
        _engine.Script.Add(Snapshot(null));
        var page = NewPage();

        var run = await StartHeld(page);

        Assert.IsFalse(page.HasActiveUploads);
        Assert.AreEqual("", page.TotalUploadSpeedText);
        Assert.IsFalse(page.Files[0].Progress!.HasProgress);
        _engine.Release();
        await run;
    }

    [TestMethod]
    public async Task An_Archive_that_has_no_row_is_shown_in_the_card()
    {
        _engine.Script.Add(Snapshot(2 * MiB, Uploading("d/dicom-d.zip", MiB, 4 * MiB, 2 * MiB)));
        var page = NewPage();

        var run = await StartHeld(page);

        Assert.AreEqual("dicom-d.zip", page.ActiveUploads.Single().Name);
        Assert.AreEqual("25%", page.ActiveUploads.Single().PercentText);
        Assert.AreEqual(0, page.Files.Count);
        _engine.Release();
        await run;
    }

    [TestMethod]
    public async Task A_finished_row_reads_size_in_Upload_Time_and_leaves_the_card()
    {
        _engine.Script.Add(File("a.ndpi", FileOutcome.Uploading));
        _engine.Script.Add(Snapshot(3 * MiB, Uploading("a.ndpi", 12 * MiB, 12 * MiB + MiB / 2, 3 * MiB)));
        _engine.Script.Add(new FileOutcomeChanged("wsi", "a.ndpi", FileOutcome.Succeeded, null, 13_002_342, TimeSpan.FromSeconds(3.2)));
        var page = NewPage();

        var run = await StartHeld(page);

        Assert.AreEqual("12.4 MiB in 3 s", page.Files.Single().Reason);
        Assert.IsFalse(page.HasActiveUploads);
        _engine.Release();
        await run;
    }

    [TestMethod]
    public async Task A_stale_snapshot_after_the_file_finished_does_not_bring_it_back()
    {
        _engine.Script.Add(new FileOutcomeChanged("wsi", "a.ndpi", FileOutcome.Succeeded, null, MiB, TimeSpan.FromSeconds(1)));
        _engine.Script.Add(Snapshot(MiB, Uploading("a.ndpi", MiB, MiB, MiB)));
        var page = NewPage();

        var run = await StartHeld(page);

        Assert.IsFalse(page.HasActiveUploads);
        _engine.Release();
        await run;
    }

    /// <summary>An engine that hands its progress sink to the test, so events can be reported while the Run is going.</summary>
    private sealed class OpenEngine : IRunEngine
    {
        private readonly TaskCompletionSource<IProgress<RunEvent>> _sink = new(TaskCreationOptions.RunContinuationsAsynchronously);
        private readonly TaskCompletionSource _end = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public Task<IProgress<RunEvent>> Sink => _sink.Task;
        public void End() => _end.TrySetResult();

        public async Task<RunResult> RunAsync(RunOptions options, IProgress<RunEvent> progress, CancellationToken cancellationToken)
        {
            _sink.SetResult(progress);
            await _end.Task;
            return new RunResult(Guid.NewGuid(), new Dictionary<FileOutcome, int>(), 0, null);
        }
    }

    [TestMethod]
    public async Task A_snapshot_touches_only_the_active_rows_in_a_large_file_list()
    {
        const int Count = 20_000;
        var engine = new OpenEngine();
        var page = new UploadPageViewModel(new FakeUploaderRuntime(Config, engine), a => a());
        var run = Start(page);
        var sink = await engine.Sink;
        for (var i = 0; i < Count; i++) sink.Report(File($"f{i}.ndpi", i == 7 ? FileOutcome.Uploading : FileOutcome.Pending));
        var rowChanges = 0;
        foreach (var row in page.Files) row.PropertyChanged += (_, _) => rowChanges++;
        var listChanges = 0;
        page.Files.CollectionChanged += (_, _) => listChanges++;

        sink.Report(Snapshot(MiB, Uploading("f7.ndpi", MiB, 10 * MiB, MiB)));

        Assert.AreEqual(Count, page.Files.Count);
        Assert.AreEqual(0, listChanges);
        Assert.AreEqual(1, page.Files.Count(r => r.Progress is not null));
        Assert.AreEqual("10%", page.ActiveUploads.Single().PercentText);
        Assert.AreEqual(0, rowChanges); // no row of the list raised anything; the one active row's progress object changed
        engine.End();
        await run;
    }

    [TestMethod]
    public void Sizes_speeds_and_times_are_binary_and_short()
    {
        Assert.AreEqual("12.4 MiB", TransferFormat.Size(13_002_342));
        Assert.AreEqual("3.1 MiB/s", TransferFormat.Speed(3.1 * MiB));
        Assert.AreEqual("<0.1 MiB/s", TransferFormat.Speed(1000));
        Assert.AreEqual("0 MiB/s", TransferFormat.Speed(0));
        Assert.AreEqual("<1 s", TransferFormat.Duration(TimeSpan.FromMilliseconds(900)));
        Assert.AreEqual("3 s", TransferFormat.Duration(TimeSpan.FromSeconds(3.2)));
        Assert.AreEqual("1 min 12 s", TransferFormat.Duration(TimeSpan.FromSeconds(72)));
        Assert.AreEqual("1 min 0 s", TransferFormat.Duration(TimeSpan.FromSeconds(59.7)));
        Assert.AreEqual("12.4 MiB in 3 s", TransferFormat.Finished(13_002_342, TimeSpan.FromSeconds(3)));
    }
}

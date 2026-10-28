using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using System.Collections.Concurrent;
using System.Collections.ObjectModel;
using System.Reactive;
using MiresSftpUploader.Core;
using ReactiveUI;

namespace MiresSftpUploader.ViewModels;

/// <summary>Which outcomes the file list is narrowed to; <see cref="None"/> shows every file, otherwise a file shows if it matches any of the set flags.</summary>
[Flags]
public enum FileFilter { None = 0, Succeeded = 1, Failed = 2, Skipped = 4, Pending = 8 }

/// <summary>
/// The Upload page: the Sources and Destination in the sidebar, Start / Dry run / Scan / Cancel, and the live
/// state of the current Run (tiles, overall progress, files). It talks to an <see cref="IUploaderRuntime"/>, so
/// tests drive it with a fake Engine and no window. Events arrive on any thread, are queued, and are applied to
/// the lists in one batch posted to the UI thread.
/// </summary>
public sealed class UploadPageViewModel : ViewModelBase
{
    private readonly IUploaderRuntime _runtime;
    private readonly RunTrigger _trigger;
    private readonly Action<Action> _post;
    private readonly ConcurrentQueue<RunEvent> _incoming = new();
    private readonly Dictionary<(string Source, string Path), FileRowViewModel> _rows = [];
    private readonly Dictionary<FileOutcome, int> _counts = [];
    private int _flushPending;
    private CancellationTokenSource? _cancellation;
    private readonly List<FileRowViewModel> _order = [];
    private Guid? _retryOf;
    private Guid? _lastRunId;

    private bool _isRunning;
    private FileFilter _filter;
    private bool _canRetry;
    private string _status = "Ready";
    private string _problems = "";
    private string _destination = "";

    /// <param name="post">Runs an action on the UI thread: <c>Dispatcher.UIThread.Post</c> in the app.</param>
    /// <param name="trigger">What starts the Runs of this page: the window (<see cref="RunTrigger.Ui"/>) or the terminal interface.</param>
    public UploadPageViewModel(IUploaderRuntime runtime, Action<Action> post, RunTrigger trigger = RunTrigger.Ui)
    {
        _runtime = runtime;
        _trigger = trigger;
        _post = post;

        var idle = this.WhenAnyValue(x => x.IsRunning, x => x.IsBlocked, (running, blocked) => !running && !blocked);
        StartCommand = ReactiveCommand.CreateFromTask(() => RunAsync(dryRun: false, retry: false), idle);
        DryRunCommand = ReactiveCommand.CreateFromTask(() => RunAsync(dryRun: true, retry: false), idle);
        ScanCommand = ReactiveCommand.CreateFromTask(() => RunAsync(dryRun: true, retry: false, scan: true), idle);
        CancelCommand = ReactiveCommand.Create(() => { _cancellation?.Cancel(); }, this.WhenAnyValue(x => x.IsRunning));
        RetryFailedCommand = ReactiveCommand.CreateFromTask(() => RunAsync(dryRun: false, retry: true), this.WhenAnyValue(x => x.CanRetry, x => x.IsBlocked, (retry, blocked) => retry && !blocked));

        Refresh();
    }

    public ObservableCollection<SourceItemViewModel> Sources { get; } = [];

    /// <summary>The files shown: all of the Run, or only those matching <see cref="Filter"/>.</summary>
    public ObservableCollection<FileRowViewModel> Files { get; } = [];

    public ReactiveCommand<Unit, Unit> StartCommand { get; }
    public ReactiveCommand<Unit, Unit> DryRunCommand { get; }
    public ReactiveCommand<Unit, Unit> ScanCommand { get; }
    public ReactiveCommand<Unit, Unit> CancelCommand { get; }
    public ReactiveCommand<Unit, Unit> RetryFailedCommand { get; }

    /// <summary>host:port of the SFTP server; empty when no host is configured.</summary>
    public string Destination
    {
        get => _destination;
        private set => this.RaiseAndSetIfChanged(ref _destination, value);
    }

    public bool IsRunning
    {
        get => _isRunning;
        private set
        {
            this.RaiseAndSetIfChanged(ref _isRunning, value);
            this.RaisePropertyChanged(nameof(IsIdle));
        }
    }

    public bool IsIdle => !IsRunning;

    private string _blockedReason = "";
    private bool _isFollowing = true;
    private string _lockRefusal = "";

    /// <summary>
    /// Whether a view should keep its cursor on <see cref="FollowIndex"/>. The view turns it off when the user moves the cursor and on again on request;
    /// "cursor on the last row" cannot stand in for it, since the mouse wheel moves the cursor too.
    /// </summary>
    public bool IsFollowing
    {
        get => _isFollowing;
        set => this.RaiseAndSetIfChanged(ref _isFollowing, value);
    }

    /// <summary>The row to follow: the first file being hashed, uploaded or verified, else the first one still Pending, else the last; -1 without files.</summary>
    public int FollowIndex
    {
        get
        {
            var waiting = -1;
            for (var i = 0; i < Files.Count; i++)
            {
                var row = Files[i];
                if (row.IsActive) return i;
                if (waiting < 0 && row.Outcome == FileOutcome.Pending) waiting = i;
            }

            return waiting >= 0 ? waiting : Files.Count - 1;
        }
    }

    /// <summary>The Run-lock refusal of the last Run ("Another Run holds the lock (…)"); empty when the last Run was not refused.</summary>
    public string LockRefusal
    {
        get => _lockRefusal;
        private set => this.RaiseAndSetIfChanged(ref _lockRefusal, value);
    }

    /// <summary>Why no Run can start (the Data Directory is not usable); empty when Runs may start. Shown as a banner.</summary>
    public string BlockedReason
    {
        get => _blockedReason;
        set
        {
            this.RaiseAndSetIfChanged(ref _blockedReason, value);
            this.RaisePropertyChanged(nameof(IsBlocked));
        }
    }

    public bool IsBlocked => _blockedReason.Length > 0;

    public bool CanRetry
    {
        get => _canRetry;
        private set => this.RaiseAndSetIfChanged(ref _canRetry, value);
    }

    /// <summary>The outcomes the file list is narrowed to. Each of the four tiles toggles its own flag: one click turns it on, another turns it off.</summary>
    public FileFilter Filter
    {
        get => _filter;
        set
        {
            if (_filter == value) return;
            this.RaiseAndSetIfChanged(ref _filter, value);
            this.RaisePropertyChanged(nameof(FilterSucceeded));
            this.RaisePropertyChanged(nameof(FilterFailed));
            this.RaisePropertyChanged(nameof(FilterSkipped));
            this.RaisePropertyChanged(nameof(FilterPending));
            RebuildFiles();
        }
    }

    public bool FilterSucceeded { get => Filter.HasFlag(FileFilter.Succeeded); set => SetFilter(FileFilter.Succeeded, value); }
    public bool FilterFailed { get => Filter.HasFlag(FileFilter.Failed); set => SetFilter(FileFilter.Failed, value); }
    public bool FilterSkipped { get => Filter.HasFlag(FileFilter.Skipped); set => SetFilter(FileFilter.Skipped, value); }
    public bool FilterPending { get => Filter.HasFlag(FileFilter.Pending); set => SetFilter(FileFilter.Pending, value); }

    private void SetFilter(FileFilter filter, bool on) => Filter = on ? Filter | filter : Filter & ~filter;

    public string Status
    {
        get => _status;
        private set => this.RaiseAndSetIfChanged(ref _status, value);
    }

    /// <summary>The configuration errors, one per line, when the configuration cannot be used; empty otherwise.</summary>
    public string Problems
    {
        get => _problems;
        private set
        {
            this.RaiseAndSetIfChanged(ref _problems, value);
            this.RaisePropertyChanged(nameof(HasProblems));
        }
    }

    public bool HasProblems => Problems.Length > 0;

    public int Succeeded => Count(FileOutcome.Succeeded);
    public int Failed => Count(FileOutcome.Failed);
    public int Skipped => Count(FileOutcome.Skipped);
    public int Ignored => Count(FileOutcome.Ignored);

    /// <summary>Files waiting or in progress: Pending, Hashing, Uploading or Verifying.</summary>
    public int Pending => Count(FileOutcome.Pending) + Count(FileOutcome.Hashing) + Count(FileOutcome.Uploading) + Count(FileOutcome.Verifying);

    /// <summary>Percent of the files that were not Ignored that have reached a final outcome.</summary>
    public double OverallProgress
    {
        get
        {
            var total = _rows.Count - Ignored;
            return total <= 0 ? 0 : 100.0 * (Succeeded + Failed + Skipped) / total;
        }
    }

    private int Count(FileOutcome outcome) => _counts.GetValueOrDefault(outcome);

    /// <summary>Reads the configuration again and refreshes the Sources and the Destination, keeping the include choices.</summary>
    public void Refresh()
    {
        var prepared = _runtime.Prepare(headless: false);
        ApplyConfiguration(prepared);
    }

    private void ApplyConfiguration(PreparedUploader prepared)
    {
        Destination = prepared.Destination;
        Problems = string.Join(Environment.NewLine, prepared.Errors.Select(e => e.ToString()));
        if (prepared.Config is not { } config) return;

        var excluded = Sources.Where(s => !s.Included).Select(s => s.Name).ToHashSet(StringComparer.OrdinalIgnoreCase);
        Sources.Clear();
        foreach (var source in config.Sources.Where(s => s.Enabled))
            Sources.Add(new SourceItemViewModel(source) { Included = !excluded.Contains(source.Name ?? "") });
    }

    /// <summary>Uploads the failed files of a Run from the Run History again, as a new Run with a fresh file list. Does nothing while a Run is going.</summary>
    public const string RunActiveNotice = "A Run is active; follow it on Upload";

    public Task RetryRunAsync(Guid runId) => IsRunning ? Task.CompletedTask : RunAsync(dryRun: false, retry: true, historical: runId);

    private async Task RunAsync(bool dryRun, bool retry, bool scan = false, Guid? historical = null)
    {
        var prepared = _runtime.Prepare(headless: false);
        ApplyConfiguration(prepared);
        if (prepared.Engine is not { } engine || prepared.Config is not { } config)
        {
            Status = $"Configuration has {prepared.Errors.Count} error(s); see Settings.";
            return;
        }

        var included = Sources.Where(s => s.Included).Select(s => s.Name).ToList();
        if (included.Count == 0)
        {
            Status = "Include at least one Source.";
            return;
        }

        if (historical is not null) _retryOf = historical;
        if (!retry || historical is not null) ClearFiles();
        var options = new RunOptions
        {
            SourceNames = included,
            DryRun = dryRun,
            RehashAll = config.Upload.RehashAll,
            Trigger = _trigger,
            RetryOf = retry ? _retryOf : null,
        };
        _lastRunId = null;
        LockRefusal = "";

        using var cancellation = new CancellationTokenSource();
        _cancellation = cancellation;
        IsRunning = true;
        CanRetry = false;
        Status = scan ? "Scanning…" : dryRun ? "Dry run…" : retry ? "Retrying failed files…" : "Running…";
        try
        {
            var result = await engine.RunAsync(options, new QueueProgress(this), cancellation.Token);
            Flush();
            Status = Describe(result, dryRun, scan);
            if (result.ExitCode == ExitCodes.LockHeld) LockRefusal = result.Reason ?? "Another Run holds the lock";
            _retryOf = dryRun ? null : _lastRunId;
        }
        catch (Exception ex) when (ex is not OperationCanceledException)
        {
            Flush();
            _retryOf = null;
            Status = $"The Run stopped unexpectedly: {ex.Message}";
        }
        finally
        {
            _cancellation = null;
            IsRunning = false;
            CanRetry = Failed > 0 && _retryOf is not null;
        }
    }

    private static string Describe(RunResult result, bool dryRun, bool scan)
    {
        if (result.ExitCode == ExitCodes.Cancelled) return "Cancelled";
        var what = scan ? "Scan" : dryRun ? "Dry run" : "Run";
        var text = $"{what} finished, exit code {result.ExitCode}";
        return string.IsNullOrWhiteSpace(result.Reason) ? text : $"{text}: {result.Reason}";
    }

    private sealed class QueueProgress(UploadPageViewModel owner) : IProgress<RunEvent>
    {
        public void Report(RunEvent value) => owner.Enqueue(value);
    }

    private void Enqueue(RunEvent value)
    {
        _incoming.Enqueue(value);
        if (Interlocked.Exchange(ref _flushPending, 1) == 0)
            _post(Flush);
    }

    private void Flush()
    {
        Interlocked.Exchange(ref _flushPending, 0);
        var changed = false;
        while (_incoming.TryDequeue(out var e))
        {
            switch (e)
            {
                case RunStarted started:
                    _lastRunId = started.RunId;
                    break;
                case FileOutcomeChanged file:
                    Apply(file);
                    changed = true;
                    break;
                case ArchivePlanned plan:
                    AddArchiveRow(plan);
                    break;
            }
        }
        if (!changed) return;
        this.RaisePropertyChanged(nameof(Succeeded));
        this.RaisePropertyChanged(nameof(Failed));
        this.RaisePropertyChanged(nameof(Skipped));
        this.RaisePropertyChanged(nameof(Ignored));
        this.RaisePropertyChanged(nameof(Pending));
        this.RaisePropertyChanged(nameof(OverallProgress));
    }

    private void Apply(FileOutcomeChanged change)
    {
        var key = (change.Source, change.RelativePath);
        var isNew = !_rows.TryGetValue(key, out var row);
        if (isNew)
        {
            row = new FileRowViewModel(change.Source, change.RelativePath);
            _rows[key] = row;
            _order.Add(row);
            _counts[row.Outcome] = Count(row.Outcome) + 1;
        }

        var wasVisible = !isNew && IsVisible(row!);
        _counts[row!.Outcome] = Count(row.Outcome) - 1;
        row.Update(change.Outcome, change.Reason);
        _counts[row.Outcome] = Count(row.Outcome) + 1;

        var visible = IsVisible(row);
        if (visible && (isNew || !wasVisible)) Files.Add(row);
        else if (!visible && wasVisible) Files.Remove(row);
    }

    /// <summary>
    /// A Dry Run's plan for one zip Archive, as a row of its own. Archive rows are not counted in the tiles, since the
    /// files in them are.
    /// </summary>
    private void AddArchiveRow(ArchivePlanned plan)
    {
        var (outcome, text) = plan.Status switch
        {
            "WouldSkip" => (FileOutcome.Skipped, "Unchanged since it was last delivered"),
            "NeedsHashing" => (FileOutcome.Pending, "Same files, but some changed size or time; they are checked again"),
            "WouldBuild" => (FileOutcome.Pending, "Would be built and uploaded"),
            var other => (other == "ArchiveNameCollision" ? FileOutcome.Failed : FileOutcome.Skipped, other),
        };
        var row = new FileRowViewModel(plan.Source, plan.Name);
        row.Update(outcome, $"Archive, rule {plan.Rule}: {plan.MemberCount} files, {FormatSize(plan.TotalSize)}. {text}");
        _order.Add(row);
        if (IsVisible(row)) Files.Add(row);
    }

    private static string FormatSize(long bytes) => bytes switch
    {
        >= 1L << 30 => $"{bytes / (double)(1L << 30):0.#} GiB",
        >= 1L << 20 => $"{bytes / (double)(1L << 20):0.#} MiB",
        >= 1L << 10 => $"{bytes / (double)(1L << 10):0.#} KiB",
        _ => $"{bytes} bytes",
    };

    private bool IsVisible(FileRowViewModel row) =>
        _filter == FileFilter.None
        || (_filter.HasFlag(FileFilter.Succeeded) && row.IsSucceeded)
        || (_filter.HasFlag(FileFilter.Failed) && row.IsFailed)
        || (_filter.HasFlag(FileFilter.Skipped) && row.Outcome == FileOutcome.Skipped)
        || (_filter.HasFlag(FileFilter.Pending) && (row.Outcome == FileOutcome.Pending || row.IsActive));

    private void RebuildFiles()
    {
        Files.Clear();
        foreach (var row in _order.Where(IsVisible)) Files.Add(row);
    }

    private void ClearFiles()
    {
        _rows.Clear();
        _order.Clear();
        _counts.Clear();
        Files.Clear();
        this.RaisePropertyChanged(nameof(Succeeded));
        this.RaisePropertyChanged(nameof(Failed));
        this.RaisePropertyChanged(nameof(Skipped));
        this.RaisePropertyChanged(nameof(Ignored));
        this.RaisePropertyChanged(nameof(Pending));
        this.RaisePropertyChanged(nameof(OverallProgress));
    }
}

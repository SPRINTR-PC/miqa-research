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

/// <summary>
/// The Upload page: the Sources and Destination in the sidebar, Start / Dry run / Scan / Cancel, and the live
/// state of the current Run (tiles, overall progress, files). It talks to an <see cref="IUploaderRuntime"/>, so
/// tests drive it with a fake Engine and no window. Events arrive on any thread, are queued, and are applied to
/// the lists in one batch posted to the UI thread.
/// </summary>
public sealed class UploadPageViewModel : ViewModelBase
{
    private readonly IUploaderRuntime _runtime;
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
    private bool _failedOnly;
    private bool _canRetry;
    private string _status = "Ready";
    private string _problems = "";
    private string _destination = "";

    /// <param name="post">Runs an action on the UI thread: <c>Dispatcher.UIThread.Post</c> in the app.</param>
    public UploadPageViewModel(IUploaderRuntime runtime, Action<Action> post)
    {
        _runtime = runtime;
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

    /// <summary>The files shown: all of the Run, or only the failed ones while <see cref="FailedOnly"/> is on.</summary>
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

    public bool FailedOnly
    {
        get => _failedOnly;
        set
        {
            if (_failedOnly == value) return;
            this.RaiseAndSetIfChanged(ref _failedOnly, value);
            RebuildFiles();
        }
    }

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

    private async Task RunAsync(bool dryRun, bool retry, bool scan = false)
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

        if (!retry) ClearFiles();
        var options = new RunOptions
        {
            SourceNames = included,
            DryRun = dryRun,
            RehashAll = config.Upload.RehashAll,
            Trigger = RunTrigger.Ui,
            RetryOf = retry ? _retryOf : null,
        };
        _lastRunId = null;

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

    private bool IsVisible(FileRowViewModel row) => !_failedOnly || row.IsFailed;

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

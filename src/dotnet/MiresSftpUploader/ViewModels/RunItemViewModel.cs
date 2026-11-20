using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Globalization;
using System.Linq;
using System.Reactive;
using MiresSftpUploader.Core;
using ReactiveUI;

namespace MiresSftpUploader.ViewModels;

/// <summary>
/// One Run in the Run History: the item in the list and, when selected, the detail pane. Its outcomes are read when the
/// item is expanded or selected. Whether the Run is the current user's decides the wording and availability of Cancel.
/// </summary>
public sealed class RunItemViewModel : ViewModelBase
{
    private readonly HistoryPageViewModel _owner;
    private RunSummary _summary;
    private bool _isExpanded;
    private FileFilter _filter;

    internal RunItemViewModel(HistoryPageViewModel owner, RunSummary summary, bool isOwn)
    {
        _owner = owner;
        _summary = summary;
        IsOwn = isOwn;

        CancelCommand = ReactiveCommand.Create(() => _owner.Cancel(this),
            this.WhenAnyValue(x => x.IsLive, x => x.CancelRequested, (isLive, requested) => isLive && !requested));
        RetryCommand = ReactiveCommand.CreateFromTask(() => _owner.RetryAsync(this),
            this.WhenAnyValue(x => x.IsLive, x => x.Failed, x => x.IsAbandoned, (isLive, failed, abandoned) => !isLive && (failed > 0 || abandoned)));
        ExportJsonCommand = ReactiveCommand.Create(() => _owner.Export(this, ReportFormat.Json));
        ExportCsvCommand = ReactiveCommand.Create(() => _owner.Export(this, ReportFormat.Csv));
    }

    public ObservableCollection<HistoryFileRow> Files { get; } = [];

    public ReactiveCommand<Unit, Unit> CancelCommand { get; }
    public ReactiveCommand<Unit, Unit> RetryCommand { get; }
    public ReactiveCommand<Unit, Unit> ExportJsonCommand { get; }
    public ReactiveCommand<Unit, Unit> ExportCsvCommand { get; }

    public RunSummary Summary => _summary;
    public Guid RunId => _summary.RunId;
    public string ShortId => _summary.RunId.ToString("N")[..8];
    public string Title => $"Run {ShortId}";

    /// <summary>Whether the current user started the Run.</summary>
    public bool IsOwn { get; }
    public bool IsOthers => !IsOwn;
    public string StartedBy => _summary.StartedBy;
    public string Who => IsOwn ? $"{StartedBy} (you)" : StartedBy;

    public bool IsLive => _summary.Status == "Running";
    public bool IsAbandoned => _summary.Status == "Abandoned";
    public bool IsDryRun => _summary.Mode == "DryRun";
    public bool CancelRequested => _summary.CancelRequested;

    /// <summary>Running, Abandoned, Cancelled, Succeeded, Failed or Finished with a non-zero exit code.</summary>
    public string StatusText => _summary.Status switch
    {
        "Running" => "Running",
        "Abandoned" => "Abandoned",
        _ => _summary.ExitCode switch
        {
            0 => "Succeeded",
            ExitCodes.Cancelled => "Cancelled",
            null => "Finished",
            _ => "Failed",
        },
    };

    public string ExitText => _summary.ExitCode is { } code ? $"Exit code {code}" : "";
    public bool NeedsAttention => IsAbandoned || (!IsLive && _summary.ExitCode is not (null or 0 or ExitCodes.Cancelled));
    public bool IsOk => StatusText == "Succeeded";

    public string ModeText => _summary.Mode switch
    {
        "DryRun" => "Dry run",
        "Retry" => "Retry",
        _ => "Run",
    };

    public string StartedText => _summary.StartedAt.ToLocalTime().ToString("yyyy-MM-dd HH:mm", CultureInfo.InvariantCulture);
    public string HeartbeatText => _summary.Heartbeat.ToLocalTime().ToString("HH:mm:ss", CultureInfo.InvariantCulture);

    public string DurationText
    {
        get
        {
            var end = _summary.EndedAt ?? _summary.Heartbeat;
            var span = end - _summary.StartedAt;
            if (span < TimeSpan.Zero) span = TimeSpan.Zero;
            return span.TotalHours >= 1 ? $"{(int)span.TotalHours} h {span.Minutes} min"
                : span.TotalMinutes >= 1 ? $"{(int)span.TotalMinutes} min {span.Seconds} s"
                : $"{(int)span.TotalSeconds} s";
        }
    }

    public int Succeeded => Count("Succeeded");
    public int Failed => Count("Failed");
    public int Skipped => Count("Skipped");

    /// <summary>Skipped files whose reason is Too Recent.</summary>
    public int TooRecent => Files.Count(f => f.Outcome == "Skipped" && f.Reason == "TooRecent");

    public int MovedAway => Count("MovedAway");
    public int Pending => Count("Pending") + Count("Hashing") + Count("Uploading") + Count("Verifying");

    /// <summary>The bytes the Run delivered: the sum over its Succeeded rows, known once the outcomes are loaded.</summary>
    public long UploadedBytes { get; private set; }

    /// <summary>The details header shows the total only for a Run that uploaded something; never for a Dry Run.</summary>
    public bool HasUploaded => !IsDryRun && UploadedBytes > 0;

    public string UploadedText => HasUploaded ? $"Uploaded {TransferFormat.Size(UploadedBytes)}" : "";

    public string CountsText => $"{Succeeded} succeeded · {Failed} failed · {Skipped} skipped";

    /// <summary>Percent of the files that were not Ignored that have reached a final outcome.</summary>
    public double Progress
    {
        get
        {
            var total = Succeeded + Failed + Skipped + MovedAway + Pending;
            return total <= 0 ? 0 : 100.0 * (total - Pending) / total;
        }
    }

    public string ProgressText => $"{Succeeded + Failed + Skipped + MovedAway} of {Succeeded + Failed + Skipped + MovedAway + Pending} files";

    public bool IsExpanded
    {
        get => _isExpanded;
        set
        {
            this.RaiseAndSetIfChanged(ref _isExpanded, value);
            if (value) _owner.LoadFiles(this);
        }
    }

    /// <summary>The outcomes the list is narrowed to, as on the Upload page: each of the Succeeded, Failed and Skipped tiles toggles its own flag.</summary>
    public FileFilter Filter
    {
        get => _filter;
        set
        {
            if (_filter == value) return;
            this.RaiseAndSetIfChanged(ref _filter, value);
            foreach (var name in new[] { nameof(FilterSucceeded), nameof(FilterFailed), nameof(FilterSkipped), nameof(FailedOnly) })
                this.RaisePropertyChanged(name);
            RebuildVisible();
        }
    }

    public bool FilterSucceeded { get => Filter.HasFlag(FileFilter.Succeeded); set => SetFilter(FileFilter.Succeeded, value); }
    public bool FilterFailed { get => Filter.HasFlag(FileFilter.Failed); set => SetFilter(FileFilter.Failed, value); }
    public bool FilterSkipped { get => Filter.HasFlag(FileFilter.Skipped); set => SetFilter(FileFilter.Skipped, value); }

    /// <summary>The Failed tile's filter under its older name (the terminal interface's "Failed only").</summary>
    public bool FailedOnly { get => FilterFailed; set => FilterFailed = value; }

    private void SetFilter(FileFilter filter, bool on) => Filter = on ? Filter | filter : Filter & ~filter;

    /// <summary>The outcomes shown: all of them, or only those matching <see cref="Filter"/>.</summary>
    public ObservableCollection<HistoryFileRow> VisibleFiles { get; } = [];

    public string CancelLabel => IsOwn ? "Cancel" : $"Request cancel ({StartedBy}'s Run)";
    public bool ShowCancelRequested => IsLive && CancelRequested;
    public bool IsLiveOthers => IsLive && IsOthers;

    internal void Update(RunSummary summary)
    {
        _summary = summary;
        foreach (var name in new[]
        {
            nameof(Summary), nameof(IsLive), nameof(IsAbandoned), nameof(CancelRequested), nameof(StatusText), nameof(ExitText),
            nameof(NeedsAttention), nameof(IsOk), nameof(HeartbeatText), nameof(DurationText), nameof(Succeeded), nameof(Failed),
            nameof(Skipped), nameof(TooRecent), nameof(MovedAway), nameof(Pending), nameof(CountsText), nameof(Progress),
            nameof(ProgressText), nameof(ShowCancelRequested), nameof(IsLiveOthers),
        })
            this.RaisePropertyChanged(name);
    }

    internal void SetFiles(IReadOnlyList<RunFileOutcome> files, long uploadedBytes)
    {
        UploadedBytes = uploadedBytes;
        Files.Clear();
        foreach (var file in files)
        {
            Files.Add(new HistoryFileRow(file));
        }
        RebuildVisible();
        this.RaisePropertyChanged(nameof(TooRecent));
        this.RaisePropertyChanged(nameof(UploadedBytes));
        this.RaisePropertyChanged(nameof(HasUploaded));
        this.RaisePropertyChanged(nameof(UploadedText));
    }

    private void RebuildVisible()
    {
        VisibleFiles.Clear();
        foreach (var row in Files.Where(f => _filter == FileFilter.None
            || (_filter.HasFlag(FileFilter.Succeeded) && f.IsSucceeded)
            || (_filter.HasFlag(FileFilter.Failed) && f.IsFailed)
            || (_filter.HasFlag(FileFilter.Skipped) && f.Outcome == "Skipped")))
            VisibleFiles.Add(row);
    }

    private int Count(string outcome) => _summary.Counts.GetValueOrDefault(outcome);
}

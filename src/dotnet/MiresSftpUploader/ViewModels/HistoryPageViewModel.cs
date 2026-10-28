using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.IO;
using System.Linq;
using System.Reactive;
using System.Threading;
using System.Threading.Tasks;
using MiresSftpUploader.Core;
using ReactiveUI;

namespace MiresSftpUploader.ViewModels;

/// <summary>
/// The History page: the Runs of the Run History (the whole machine's, not only this user's) with the filters All /
/// Needs attention / Live now, and the selected Run in full. Live Runs are followed with <see cref="IRunHistory.WatchRun"/>.
/// Cancel works on any live Run through a cancel request; Retry starts a new Run through the supplied callback.
/// </summary>
public sealed class HistoryPageViewModel : ViewModelBase, IDisposable
{
    public const int ListLimit = 200;
    public static IReadOnlyList<string> FilterNames { get; } = ["All", "Needs attention", "Live now"];

    private readonly IRunHistory _history;
    private readonly string _currentUser;
    private readonly Action<Action> _post;
    private readonly Func<Guid, Task<string?>> _retry;
    private readonly Dictionary<Guid, CancellationTokenSource> _watches = [];
    private readonly CancellationTokenSource _lifetime = new();
    private RunFilterKind _filter = RunFilterKind.All;
    private RunItemViewModel? _selected;
    private string _notice = "";

    /// <param name="currentUser">The account name of this user; Runs started by it are "own".</param>
    /// <param name="post">Runs an action on the UI thread: <c>Dispatcher.UIThread.Post</c> in the app.</param>
    /// <param name="retry">Starts a Run that uploads the failed files of the given Run again.</param>
    public HistoryPageViewModel(IRunHistory history, string currentUser, Action<Action> post, Func<Guid, Task<string?>> retry)
    {
        _history = history;
        _currentUser = currentUser;
        _post = post;
        _retry = retry;
        RefreshCommand = ReactiveCommand.Create(Refresh);
        Refresh();
    }

    public ObservableCollection<RunItemViewModel> Runs { get; } = [];

    public ReactiveCommand<Unit, Unit> RefreshCommand { get; }

    public RunFilterKind Filter
    {
        get => _filter;
        set
        {
            if (_filter == value) return;
            this.RaiseAndSetIfChanged(ref _filter, value);
            this.RaisePropertyChanged(nameof(FilterIndex));
            Refresh();
        }
    }

    /// <summary>The position in <see cref="FilterNames"/>; for the filter list in the view.</summary>
    public int FilterIndex
    {
        get => (int)_filter;
        set => Filter = (RunFilterKind)Math.Clamp(value, 0, FilterNames.Count - 1);
    }

    public RunItemViewModel? Selected
    {
        get => _selected;
        set
        {
            this.RaiseAndSetIfChanged(ref _selected, value);
            this.RaisePropertyChanged(nameof(HasSelection));
            if (value is not null) LoadFiles(value);
        }
    }

    public bool HasSelection => Selected is not null;
    public bool IsEmpty => Runs.Count == 0;

    /// <summary>The result of the last Cancel or Export, or why it did not work; empty when there is nothing to say.</summary>
    public string Notice
    {
        get => _notice;
        private set
        {
            this.RaiseAndSetIfChanged(ref _notice, value);
            this.RaisePropertyChanged(nameof(HasNotice));
        }
    }

    public bool HasNotice => Notice.Length > 0;

    /// <summary>Reads the Run History again, keeping the selection and expanded Runs, and follows the live Runs.</summary>
    public void Refresh()
    {
        _history.SweepAbandoned();
        var summaries = _history.ListRuns(new RunFilter { Kind = _filter, Limit = ListLimit });
        var expanded = Runs.Where(r => r.IsExpanded).Select(r => r.RunId).ToHashSet();
        var selectedId = Selected?.RunId;

        StopWatching();
        Runs.Clear();
        foreach (var summary in summaries)
        {
            var item = new RunItemViewModel(this, summary, IsOwn(summary));
            Runs.Add(item);
            if (expanded.Contains(item.RunId)) item.IsExpanded = true;
            if (item.IsLive) Watch(item);
        }
        this.RaisePropertyChanged(nameof(IsEmpty));
        Selected = selectedId is { } id ? Runs.FirstOrDefault(r => r.RunId == id) : null;
    }

    private bool IsOwn(RunSummary summary) => string.Equals(summary.StartedBy, _currentUser, StringComparison.OrdinalIgnoreCase);

    internal void LoadFiles(RunItemViewModel item)
    {
        if (_history.GetRun(item.RunId) is { } detail)
        {
            item.Update(detail.Summary);
            item.SetFiles(detail.Files);
        }
    }

    internal void Cancel(RunItemViewModel item)
    {
        var accepted = _history.RequestCancel(item.RunId);
        Notice = accepted
            ? item.IsOwn ? "Cancel requested." : $"Cancel requested of {item.StartedBy}'s Run."
            : "The Run has already ended.";
        if (_history.GetRun(item.RunId) is { } detail) item.Update(detail.Summary);
    }

    internal async Task RetryAsync(RunItemViewModel item)
    {
        if (await _retry(item.RunId) is { Length: > 0 } notice) Notice = notice;
    }

    internal void Export(RunItemViewModel item, ReportFormat format)
    {
        try
        {
            Notice = _history.SaveReport(item.RunId, format) is { } path
                ? $"Report written: {path}"
                : "The Run is no longer in the Run History.";
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            Notice = $"The Report could not be written: {ex.Message}";
        }
    }

    private void Watch(RunItemViewModel item)
    {
        var cancellation = CancellationTokenSource.CreateLinkedTokenSource(_lifetime.Token);
        _watches[item.RunId] = cancellation;
        _ = Task.Run(async () =>
        {
            try
            {
                await foreach (var detail in _history.WatchRun(item.RunId, cancellation.Token))
                    _post(() => Apply(item, detail));
            }
            catch (OperationCanceledException)
            {
            }
        });
    }

    private void Apply(RunItemViewModel item, RunDetail detail)
    {
        item.Update(detail.Summary);
        if (item.IsExpanded || ReferenceEquals(item, Selected) || !item.IsLive) item.SetFiles(detail.Files);
    }

    private void StopWatching()
    {
        foreach (var watch in _watches.Values) watch.Cancel();
        _watches.Clear();
    }

    public void Dispose()
    {
        _lifetime.Cancel();
        StopWatching();
    }
}

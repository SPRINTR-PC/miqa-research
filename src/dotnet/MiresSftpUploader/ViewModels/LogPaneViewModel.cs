using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Linq;
using System.Threading;
using Microsoft.Extensions.Logging;
using MiresSftpUploader.Logging;
using ReactiveUI;

namespace MiresSftpUploader.ViewModels;

/// <summary>
/// The log pane: entries arrive on any thread, are buffered, and are moved to <see cref="Entries"/> in one batch
/// posted to the UI thread. <see cref="MinimumLevel"/> filters what is shown without discarding what was kept.
/// </summary>
public sealed class LogPaneViewModel : ViewModelBase
{
    private readonly ConcurrentQueue<LogEntry> _incoming = new();
    private readonly List<LogEntry> _kept = [];
    private readonly Action<Action> _post;
    private readonly int _capacity;
    private int _flushPending;
    private LogLevel _minimumLevel;

    /// <param name="post">Runs an action on the UI thread: <c>Dispatcher.UIThread.Post</c> in the app.</param>
    /// <param name="capacity">How many of the newest entries to keep, whatever their level.</param>
    public LogPaneViewModel(UiLogTarget source, Action<Action> post, LogLevel minimumLevel, int capacity = 5000)
    {
        _post = post;
        _minimumLevel = minimumLevel;
        _capacity = capacity;
        source.LogReceived += OnLogReceived;
    }

    /// <summary>The levels the pane's filter offers.</summary>
    public static IReadOnlyList<LogLevel> SelectableLevels { get; } = [LogLevel.Debug, LogLevel.Information, LogLevel.Warning, LogLevel.Error];

    /// <summary>The entries at or above <see cref="MinimumLevel"/>, oldest first. Only touched on the UI thread.</summary>
    public ObservableCollection<LogEntry> Entries { get; } = [];

    public LogLevel MinimumLevel
    {
        get => _minimumLevel;
        set
        {
            if (_minimumLevel == value) return;
            this.RaiseAndSetIfChanged(ref _minimumLevel, value);
            Rebuild();
        }
    }

    private void OnLogReceived(LogEntry entry)
    {
        _incoming.Enqueue(entry);
        if (Interlocked.Exchange(ref _flushPending, 1) == 0)
            _post(Flush);
    }

    private void Flush()
    {
        Interlocked.Exchange(ref _flushPending, 0);
        var added = 0;
        while (_incoming.TryDequeue(out var entry))
        {
            _kept.Add(entry);
            added++;
            if (entry.Level >= _minimumLevel) Entries.Add(entry);
        }
        if (added == 0) return;

        var excess = _kept.Count - _capacity;
        if (excess > 0)
        {
            _kept.RemoveRange(0, excess);
            Rebuild();
        }
    }

    private void Rebuild()
    {
        Entries.Clear();
        foreach (var entry in _kept.Where(e => e.Level >= _minimumLevel))
            Entries.Add(entry);
    }
}

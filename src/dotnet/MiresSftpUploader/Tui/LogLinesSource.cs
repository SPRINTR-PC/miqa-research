using System;
using System.Collections;
using System.Collections.ObjectModel;
using System.Collections.Specialized;
using System.Linq;
using MiresSftpUploader.Logging;
using Terminal.Gui.Views;

namespace MiresSftpUploader.Tui;

/// <summary>
/// The Log pane's entries as a list that reads the collection live. A <c>ListWrapper</c> over an <see cref="ObservableCollection{T}"/> formats and
/// re-measures every entry on every change (31 s for 5,000 appends); this one formats only what it draws and raises no per-item events.
/// </summary>
public sealed class LogLinesSource(ObservableCollection<LogEntry> entries) : IListDataSource, IDisposable
{
    public event NotifyCollectionChangedEventHandler? CollectionChanged
    {
        add { }
        remove { }
    }

    public int Count => entries.Count;

    public int MaxItemLength => 200;

    public bool SuspendCollectionChangedEvent { get; set; }

    public static string Format(LogEntry e) => $"{e.Time:HH:mm:ss} {e.Level.ToString().ToUpperInvariant()[..Math.Min(4, e.Level.ToString().Length)]} {e.Message}";

    public void Render(ListView container, bool selected, int item, int col, int line, int width, int viewportX = 0)
    {
        container.Move(col, line);
        var text = item >= 0 && item < entries.Count ? Format(entries[item]) : "";
        text = viewportX < text.Length ? text[viewportX..] : "";
        if (text.Length > width) text = text[..width];
        container.AddStr(text.PadRight(width));
    }

    public bool IsMarked(int item) => false;

    public void SetMark(int item, bool value)
    {
    }

    public IList ToList() => entries.Select(Format).ToList();

    public void Dispose()
    {
    }
}

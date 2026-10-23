using Microsoft.Extensions.Logging;
using MiresSftpUploader.Logging;
using MiresSftpUploader.ViewModels;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class LogPaneViewModelTests
{
    private readonly List<Action> _posted = [];
    private readonly UiLogTarget _target = new();

    private LogPaneViewModel NewPane(LogLevel level = LogLevel.Information, int capacity = 1000) =>
        new(_target, _posted.Add, level, capacity);

    private void Emit(LogLevel level, string message) =>
        _target.Emit(new LogEntry(DateTimeOffset.UnixEpoch, level, "Test", message));

    private void RunPosted()
    {
        var work = _posted.ToList();
        _posted.Clear();
        foreach (var a in work) a();
    }

    [TestMethod]
    public void Entries_are_buffered_and_reach_the_pane_in_one_post_on_the_UI_thread()
    {
        var pane = NewPane();

        Emit(LogLevel.Information, "one");
        Emit(LogLevel.Warning, "two");
        Emit(LogLevel.Error, "three");

        Assert.HasCount(1, _posted, "a burst of entries asks the UI thread for one update");
        Assert.IsEmpty(pane.Entries, "nothing is visible before the UI thread runs");
        RunPosted();
        CollectionAssert.AreEqual(new[] { "one", "two", "three" }, pane.Entries.Select(e => e.Message).ToArray());

        Emit(LogLevel.Information, "four");
        Assert.HasCount(1, _posted, "a later entry asks again");
    }

    [TestMethod]
    public void The_level_filter_hides_lower_levels_and_changing_it_re_filters_what_was_kept()
    {
        var pane = NewPane(LogLevel.Warning);
        Emit(LogLevel.Debug, "debug");
        Emit(LogLevel.Information, "info");
        Emit(LogLevel.Warning, "warn");
        Emit(LogLevel.Error, "error");
        RunPosted();

        CollectionAssert.AreEqual(new[] { "warn", "error" }, pane.Entries.Select(e => e.Message).ToArray());

        pane.MinimumLevel = LogLevel.Information;
        CollectionAssert.AreEqual(new[] { "info", "warn", "error" }, pane.Entries.Select(e => e.Message).ToArray());
    }

    [TestMethod]
    public void The_pane_keeps_only_the_newest_entries()
    {
        var pane = NewPane(capacity: 3);
        for (var i = 1; i <= 5; i++) Emit(LogLevel.Information, $"m{i}");
        RunPosted();

        CollectionAssert.AreEqual(new[] { "m3", "m4", "m5" }, pane.Entries.Select(e => e.Message).ToArray());
    }
}

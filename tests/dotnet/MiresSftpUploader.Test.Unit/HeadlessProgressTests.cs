using System.Text;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Time.Testing;
using MiresSftpUploader.Core;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class HeadlessProgressTests
{
    private const double MiB = 1024 * 1024;

    private readonly FakeTimeProvider _time = new(new DateTimeOffset(2026, 6, 1, 12, 0, 0, TimeSpan.Zero));
    private readonly StringWriter _raw = new();
    private readonly CapturingLoggerProvider _logs = new();
    private int _width = 80;

    private StatusLineWriter Writer() => new(_raw, () => _width);

    private HeadlessProgress Progress(StatusLineWriter? status) =>
        new(status, LoggerFactory.Create(b => b.AddProvider(_logs)), _time);

    /// <summary>What a terminal would show for what was written: carriage return goes to the line start, characters overwrite.</summary>
    private static string[] Screen(string written)
    {
        var lines = new List<StringBuilder> { new() };
        var column = 0;
        foreach (var c in written)
        {
            var line = lines[^1];
            if (c == '\r') column = 0;
            else if (c == '\n') { lines.Add(new StringBuilder()); column = 0; }
            else
            {
                if (column < line.Length) line[column] = c; else line.Append(c);
                column++;
            }
        }
        return lines.Select(l => l.ToString().TrimEnd()).ToArray();
    }

    private static void Outcomes(HeadlessProgress p, int total, int done, int ignored = 0)
    {
        for (var i = 0; i < total; i++)
            p.Report(new FileOutcomeChanged("s", $"f{i}", FileOutcome.Pending, null));
        for (var i = 0; i < done; i++)
            p.Report(new FileOutcomeChanged("s", $"f{i}", i % 3 == 0 ? FileOutcome.Succeeded : i % 3 == 1 ? FileOutcome.Failed : FileOutcome.Skipped, null));
        for (var i = 0; i < ignored; i++)
            p.Report(new FileOutcomeChanged("s", $"i{i}", FileOutcome.Ignored, null));
    }

    private static UploadProgress Snapshot(int uploading, double? total) =>
        new(Enumerable.Range(0, uploading).Select(i => new UploadingFile("s", $"u{i}", 10, 100, null)).ToList(), total);

    [TestMethod]
    public void A_snapshot_draws_speed_uploading_count_and_files_done_binary_units_and_grouped_thousands()
    {
        var status = Writer();
        using var p = Progress(status);
        Outcomes(p, total: 1280, done: 412, ignored: 5);

        p.Report(Snapshot(3, 9.2 * MiB));

        CollectionAssert.AreEqual(new[] { "↑ 9.2 MiB/s · 3 uploading · 412 of 1,280 files done" }, Screen(_raw.ToString()));
    }

    [TestMethod]
    public void Speed_and_uploading_count_are_dropped_when_nothing_uploads()
    {
        var status = Writer();
        using var p = Progress(status);
        Outcomes(p, total: 4, done: 2);
        p.Report(Snapshot(1, 1 * MiB));

        p.Report(Snapshot(0, null));

        CollectionAssert.AreEqual(new[] { "2 of 4 files done" }, Screen(_raw.ToString()));
    }

    [TestMethod]
    public void An_unmeasured_speed_leaves_out_only_the_speed()
    {
        var status = Writer();
        using var p = Progress(status);
        Outcomes(p, total: 4, done: 0);

        p.Report(Snapshot(2, null));

        CollectionAssert.AreEqual(new[] { "2 uploading · 0 of 4 files done" }, Screen(_raw.ToString()));
    }

    [TestMethod]
    public void The_status_line_is_cut_to_the_window_width_so_it_never_wraps()
    {
        _width = 20;
        var status = Writer();
        using var p = Progress(status);
        Outcomes(p, total: 4, done: 0);

        p.Report(Snapshot(2, 9.2 * MiB));

        var line = Screen(_raw.ToString()).Single();
        Assert.AreEqual("↑ 9.2 MiB/s · 2 upl", line);
        Assert.IsTrue(line.Length < _width);
    }

    [TestMethod]
    public void A_shorter_redraw_leaves_nothing_of_the_longer_one_behind()
    {
        var status = Writer();
        using var p = Progress(status);
        Outcomes(p, total: 4, done: 0);
        p.Report(Snapshot(2, 10.2 * MiB));

        p.Report(Snapshot(0, null));

        CollectionAssert.AreEqual(new[] { "0 of 4 files done" }, Screen(_raw.ToString()));
    }

    [TestMethod]
    public void A_log_line_is_never_written_on_the_status_line_and_the_status_is_redrawn_below_it()
    {
        var status = Writer();
        using var p = Progress(status);
        Outcomes(p, total: 4, done: 0);
        p.Report(Snapshot(2, 1 * MiB));

        status.WriteLine("2026-06-01|WARN|Engine|something happened");
        status.Write("half a line");
        status.WriteLine(" finished");

        CollectionAssert.AreEqual(
            new[] { "2026-06-01|WARN|Engine|something happened", "half a line finished", "↑ 1.0 MiB/s · 2 uploading · 0 of 4 files done" },
            Screen(_raw.ToString()));
    }

    [TestMethod]
    public void Clearing_removes_the_status_line_and_a_late_snapshot_does_not_bring_it_back()
    {
        var status = Writer();
        using var p = Progress(status);
        Outcomes(p, total: 4, done: 0);
        p.Report(Snapshot(2, 1 * MiB));

        status.Clear();
        p.Report(Snapshot(2, 1 * MiB));
        status.WriteLine("last line");

        CollectionAssert.AreEqual(new[] { "last line", "" }, Screen(_raw.ToString()));
    }

    [TestMethod]
    public void Without_a_status_writer_nothing_is_drawn_but_the_log_line_still_comes()
    {
        using var p = Progress(null);
        Outcomes(p, total: 2, done: 0);
        p.Report(Snapshot(1, 1 * MiB));

        _time.Advance(HeadlessProgress.LogInterval);

        Assert.AreEqual("", _raw.ToString());
        Assert.AreEqual(1, _logs.Entries.Count);
    }

    [TestMethod]
    public void Every_10_seconds_while_files_upload_one_line_is_logged_under_its_own_logger_name()
    {
        var status = Writer();
        using var p = Progress(status);
        Outcomes(p, total: 1280, done: 412);
        p.Report(Snapshot(3, 9.2 * MiB));

        _time.Advance(TimeSpan.FromSeconds(9));
        Assert.AreEqual(0, _logs.Entries.Count);
        _time.Advance(TimeSpan.FromSeconds(1));
        _time.Advance(HeadlessProgress.LogInterval);

        Assert.AreEqual(2, _logs.Entries.Count);
        var entry = _logs.Entries[0];
        Assert.AreEqual("progress: 412 of 1,280 files done, 3 uploading, 9.2 MiB/s", entry.Message);
        Assert.AreEqual(LogLevel.Information, entry.Level);
        Assert.AreEqual(HeadlessProgress.LoggerName, entry.Category);
    }

    [TestMethod]
    public void Nothing_is_logged_while_nothing_uploads()
    {
        using var p = Progress(Writer());
        Outcomes(p, total: 3, done: 3);

        _time.Advance(TimeSpan.FromSeconds(30));
        p.Report(Snapshot(1, 1 * MiB));
        p.Report(Snapshot(0, null));
        _time.Advance(TimeSpan.FromSeconds(30));

        Assert.AreEqual(0, _logs.Entries.Count);
    }

    [TestMethod]
    public void A_disposed_progress_logs_nothing_more()
    {
        var p = Progress(null);
        p.Report(Snapshot(1, 1 * MiB));
        p.Dispose();

        _time.Advance(TimeSpan.FromSeconds(30));

        Assert.AreEqual(0, _logs.Entries.Count);
    }

    [TestMethod]
    [DataRow(false, "xterm-256color", null, true)]
    [DataRow(false, null, null, true)]
    [DataRow(false, null, "", true)]
    [DataRow(true, "xterm-256color", null, false)]
    [DataRow(false, "dumb", null, false)]
    [DataRow(false, "xterm", "true", false)]
    public void The_status_line_is_for_an_interactive_stderr_only(bool redirected, string? term, string? ci, bool expected) =>
        Assert.AreEqual(expected, StatusLineWriter.IsInteractive(redirected, term, ci));
}

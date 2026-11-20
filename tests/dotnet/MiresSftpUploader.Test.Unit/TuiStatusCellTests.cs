using System.Reactive.Threading.Tasks;
using MiresSftpUploader.Core;
using MiresSftpUploader.Test.Support;
using MiresSftpUploader.Tui;
using MiresSftpUploader.ViewModels;

namespace MiresSftpUploader.Test.Unit;

/// <summary>The Status cell of an Upload page row in the TUI: bar, percent and Upload Speed while uploading, "Succeeded 12.4 MiB in 3 s" when finished.</summary>
[TestClass]
public sealed class TuiStatusCellTests
{
    private const long MiB = 1L << 20;

    private static readonly AppConfig Config = new()
    {
        Sftp = new SftpConfig { Host = "sftp.mires.example", Port = 22 },
        Sources = [new SourceConfig { Name = "wsi", Path = "/data/wsi" }],
    };

    /// <summary>A row of the real view model after the given events, with the Run still held.</summary>
    private async Task<(FileRowViewModel Row, Func<Task> Finish)> RowAfter(params RunEvent[] events)
    {
        var engine = new FakeRunEngine { Hold = true };
        engine.Script.AddRange(events);
        var page = new UploadPageViewModel(new FakeUploaderRuntime(Config, engine), post: a => a());
        var run = page.StartCommand.Execute().ToTask();
        await engine.Started;
        return (page.Files[0], async () =>
        {
            engine.Release();
            await run;
        });
    }

    private static FileOutcomeChanged File(FileOutcome outcome, string? reason = null, long? sent = null, TimeSpan? time = null) =>
        new("wsi", "a.ndpi", outcome, reason, sent, time);

    private static UploadProgress Snapshot(long sent, long total, double? speed) =>
        new([new UploadingFile("wsi", "a.ndpi", sent, total, speed)], speed);

    private async Task<string> Uploading(long sent, long total, double? speed, int width)
    {
        var (row, finish) = await RowAfter(File(FileOutcome.Uploading), Snapshot(sent, total, speed));
        var text = TuiStatusCell.Of(row, width);
        await finish();
        return text;
    }

    [TestMethod]
    public async Task An_uploading_row_shows_bar_percent_and_speed()
    {
        Assert.AreEqual("███░░░░░ 42% 3.1 MiB/s", await Uploading(42 * MiB, 100 * MiB, 3.1 * MiB, 40));
    }

    [TestMethod]
    public async Task The_bar_is_full_at_100_percent_and_empty_at_0()
    {
        Assert.AreEqual("████████ 100% 1.0 MiB/s", await Uploading(10 * MiB, 10 * MiB, 1.0 * MiB, 40));
        Assert.AreEqual("░░░░░░░░ 0% 1.0 MiB/s", await Uploading(0, 10 * MiB, 1.0 * MiB, 40));
    }

    [TestMethod]
    public async Task An_uploading_row_shows_no_bar_or_speed_before_two_samples()
    {
        Assert.AreEqual("Uploading", await Uploading(5 * MiB, 10 * MiB, null, 40));

        var (row, finish) = await RowAfter(File(FileOutcome.Uploading));
        Assert.AreEqual("Uploading", TuiStatusCell.Of(row, 40));
        await finish();
    }

    [TestMethod]
    public async Task A_narrow_cell_drops_the_bar_first_and_keeps_percent_and_speed()
    {
        Assert.AreEqual("███░░░░░ 42% 3.1 MiB/s", await Uploading(42 * MiB, 100 * MiB, 3.1 * MiB, 22));
        Assert.AreEqual("42% 3.1 MiB/s", await Uploading(42 * MiB, 100 * MiB, 3.1 * MiB, 21));
        Assert.AreEqual("42% 3.1 MiB/s", await Uploading(42 * MiB, 100 * MiB, 3.1 * MiB, 5));
    }

    [TestMethod]
    public async Task A_wider_speed_text_keeps_the_bar_only_when_everything_fits()
    {
        Assert.AreEqual("42% 112.4 MiB/s", await Uploading(42 * MiB, 100 * MiB, 112.4 * MiB, 23));
        Assert.AreEqual("███░░░░░ 42% 112.4 MiB/s", await Uploading(42 * MiB, 100 * MiB, 112.4 * MiB, 24));
    }

    [TestMethod]
    public async Task A_succeeded_row_shows_what_was_sent_and_how_long_it_took()
    {
        var (row, finish) = await RowAfter(File(FileOutcome.Succeeded, sent: 13_002_342, time: TimeSpan.FromSeconds(3)));
        Assert.AreEqual("Succeeded 12.4 MiB in 3 s", TuiStatusCell.Of(row, 40));
        await finish();

        (row, finish) = await RowAfter(File(FileOutcome.Succeeded));
        Assert.AreEqual("Succeeded", TuiStatusCell.Of(row, 40));
        await finish();
    }

    [TestMethod]
    public async Task Other_rows_show_the_reason_or_the_outcome_as_before()
    {
        var (row, finish) = await RowAfter(File(FileOutcome.Failed, "connection reset"));
        Assert.AreEqual("connection reset", TuiStatusCell.Of(row, 40));
        await finish();

        (row, finish) = await RowAfter(File(FileOutcome.Hashing));
        Assert.AreEqual("Hashing", TuiStatusCell.Of(row, 40));
        await finish();
    }
}

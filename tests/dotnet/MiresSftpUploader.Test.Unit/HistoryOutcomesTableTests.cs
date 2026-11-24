using MiresSftpUploader.Core;
using MiresSftpUploader.Test.Support;
using MiresSftpUploader.Tui;
using MiresSftpUploader.ViewModels;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class HistoryOutcomesTableTests
{
    [TestMethod]
    public void The_TUI_Status_cell_carries_the_transfer_text_after_the_outcome()
    {
        var history = new FakeRunHistory();
        history.Add(counts: new Dictionary<string, int> { ["Succeeded"] = 2 }, files:
        [
            new RunFileOutcome("wsi", "new.svs", "Succeeded", 13_002_342, 99999, null, 3000),
            new RunFileOutcome("wsi", "old.svs", "Succeeded", 13_002_342, 99999, null, null),
        ]);
        var run = new HistoryPageViewModel(history, "anna", a => a(), _ => Task.FromResult<string?>(null)).Runs.Single();
        run.IsExpanded = true;

        var table = new RunOutcomesSource(() => run.VisibleFiles);

        Assert.AreEqual("Succeeded 12.4 MiB in 3 s · 4.1 MiB/s", table[0, 3]);
        Assert.AreEqual("Succeeded", table[1, 3]);
    }
}

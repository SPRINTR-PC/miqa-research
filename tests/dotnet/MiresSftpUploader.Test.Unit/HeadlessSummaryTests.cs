using MiresSftpUploader.Core;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class HeadlessSummaryTests
{
    private static RunResult Result(int exitCode, params (FileOutcome Outcome, int Count)[] counts) =>
        new(Guid.Empty, counts.ToDictionary(c => c.Outcome, c => c.Count), exitCode, null);

    [TestMethod]
    public void Summary_is_one_line_with_counts_exit_code_and_Report_path()
    {
        var line = HeadlessSummary.Format(Result(1, (FileOutcome.Succeeded, 10), (FileOutcome.Skipped, 3), (FileOutcome.Failed, 2)), "/data/reports/run-1.json");

        Assert.AreEqual("succeeded=10 skipped=3 failed=2 exit=1 report=/data/reports/run-1.json", line);
    }

    [TestMethod]
    public void Summary_without_a_Report_says_so_and_counts_missing_outcomes_as_zero()
    {
        var line = HeadlessSummary.Format(Result(0), null);

        Assert.AreEqual("succeeded=0 skipped=0 failed=0 exit=0 report=-", line);
    }
}

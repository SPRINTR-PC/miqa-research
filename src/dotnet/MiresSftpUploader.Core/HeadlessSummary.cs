namespace MiresSftpUploader.Core;

/// <summary>
/// The only thing a Headless Run writes to stdout: one line with the counts, the exit code and the Report path,
/// so a script can read it. Everything else, including logs, goes to stderr or the log file.
/// </summary>
public static class HeadlessSummary
{
    public static string Format(RunResult result, string? reportPath) =>
        $"succeeded={result.Count(FileOutcome.Succeeded)} skipped={result.Count(FileOutcome.Skipped)} failed={result.Count(FileOutcome.Failed)} exit={result.ExitCode} report={reportPath ?? "-"}";

    public static void Write(TextWriter stdout, RunResult result, string? reportPath) =>
        stdout.WriteLine(Format(result, reportPath));
}

namespace MiresSftpUploader.Core;

/// <summary>
/// The only thing a Headless Run writes to stdout: one line with the counts, the exit code and the Report path,
/// so a script can read it. Everything else, including logs, goes to stderr or the log file.
/// </summary>
public static class HeadlessSummary
{
    public static string Format(RunResult result, string? reportPath)
    {
        var line = $"succeeded={result.Count(FileOutcome.Succeeded)} skipped={result.Count(FileOutcome.Skipped)} failed={result.Count(FileOutcome.Failed)} exit={result.ExitCode} report={reportPath ?? "-"}";
        // Only when Verification took place, so the line of a Run without it keeps its shape.
        return result.Verified > 0 || result.VerificationFailures > 0
            ? $"{line} verified={result.Verified} verification_failed={result.VerificationFailures}"
            : line;
    }

    public static void Write(TextWriter stdout, RunResult result, string? reportPath) =>
        stdout.WriteLine(Format(result, reportPath));
}

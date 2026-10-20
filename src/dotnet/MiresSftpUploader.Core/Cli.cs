using System.Globalization;

namespace MiresSftpUploader.Core;

/// <summary>The <c>--report</c> and <c>--report-format</c> flags: where a Run writes its Report, and in which format.</summary>
public sealed record ReportOptions(string? Path, ReportFormat? Format);

/// <summary>
/// The command-line surface that needs no window: <c>--version</c>, <c>--help</c>, <c>--list-runs</c>, <c>--export-run</c>,
/// and unknown-flag rejection. stdout carries only the result; diagnostics go to stderr.
/// </summary>
public static class Cli
{
    private static readonly string[] KnownFlags =
        ["--headless", "--version", "--help", "--list-runs", "--limit", "--export-run", "--report", "--report-format"];

    /// <summary>
    /// Handles the arguments when they ask for something that does not need the window.
    /// Returns false when the caller should go on to start the UI (or a Headless Run).
    /// <paramref name="state"/> locates the Upload State for the Run History commands.
    /// </summary>
    public static bool TryRun(string[] args, string version, TextWriter stdout, TextWriter stderr, out int exitCode, StateSettings? state = null)
    {
        exitCode = ExitCodes.Ok;
        if (args.Length == 0) return false;

        var unknown = args.FirstOrDefault(a => a.StartsWith("--", StringComparison.Ordinal) && !KnownFlags.Contains(a));
        if (unknown is not null)
        {
            stderr.WriteLine($"Unknown option '{unknown}'. Use --help to list the options.");
            exitCode = ExitCodes.ConfigurationError;
            return true;
        }

        if (args.Contains("--version"))
        {
            stdout.WriteLine(version);
            return true;
        }

        if (args.Contains("--help"))
        {
            stdout.Write(HelpText);
            return true;
        }

        if (args.Contains("--list-runs"))
        {
            exitCode = ListRuns(args, stdout, stderr, state);
            return true;
        }

        if (args.Contains("--export-run"))
        {
            exitCode = ExportRun(args, stdout, stderr, state);
            return true;
        }

        return false;
    }

    /// <summary>Reads <c>--report</c> and <c>--report-format</c>; false with a message when the format is not <c>json</c> or <c>csv</c> or a value is missing.</summary>
    public static bool TryParseReportOptions(string[] args, out ReportOptions options, out string? error)
    {
        options = new ReportOptions(null, null);
        error = null;
        string? path = null;
        ReportFormat? format = null;

        if (args.Contains("--report"))
        {
            path = ValueOf(args, "--report");
            if (path is null) { error = "--report needs a path."; return false; }
        }
        if (args.Contains("--report-format"))
        {
            var value = ValueOf(args, "--report-format");
            if (value is null || !Enum.TryParse<ReportFormat>(value, ignoreCase: true, out var parsed) || !Enum.IsDefined(parsed))
            {
                error = "--report-format must be json or csv.";
                return false;
            }
            format = parsed;
        }
        options = new ReportOptions(path, format);
        return true;
    }

    private static int ListRuns(string[] args, TextWriter stdout, TextWriter stderr, StateSettings? state)
    {
        int? limit = null;
        if (args.Contains("--limit"))
        {
            if (!int.TryParse(ValueOf(args, "--limit"), NumberStyles.None, CultureInfo.InvariantCulture, out var parsed) || parsed < 1)
            {
                stderr.WriteLine("--limit must be a positive whole number.");
                return ExitCodes.ConfigurationError;
            }
            limit = parsed;
        }
        if (!HasState(state, stderr)) return ExitCodes.ConfigurationError;

        foreach (var run in new RunHistory(state!, TimeProvider.System).ListRuns(new RunFilter { Limit = limit }))
        {
            var counts = string.Join(' ', run.Counts.OrderBy(kv => kv.Key, StringComparer.Ordinal).Select(kv => $"{kv.Key}={kv.Value}"));
            stdout.WriteLine(string.Join('\t', run.RunId, run.Status, run.ExitCode?.ToString(CultureInfo.InvariantCulture) ?? "-",
                run.StartedAt.ToString("O", CultureInfo.InvariantCulture), run.StartedBy, run.Mode, counts));
        }
        return ExitCodes.Ok;
    }

    private static int ExportRun(string[] args, TextWriter stdout, TextWriter stderr, StateSettings? state)
    {
        if (!Guid.TryParse(ValueOf(args, "--export-run"), out var runId))
        {
            stderr.WriteLine("--export-run needs a Run id.");
            return ExitCodes.ConfigurationError;
        }
        if (!TryParseReportOptions(args, out var report, out var error))
        {
            stderr.WriteLine(error);
            return ExitCodes.ConfigurationError;
        }
        if (!HasState(state, stderr)) return ExitCodes.ConfigurationError;

        var format = report.Format ?? ReportFormat.Json;
        var text = new RunHistory(state!, TimeProvider.System).Export(runId, format);
        if (text is null)
        {
            stderr.WriteLine($"No Run {runId} in the Upload State.");
            return ExitCodes.ConfigurationError;
        }

        if (report.Path is null)
        {
            stdout.Write(text);
            return ExitCodes.Ok;
        }
        try
        {
            ReportWriter.WriteFile(report.Path, text);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            stderr.WriteLine($"Could not write the Report to {report.Path}: {ex.Message}");
            return ExitCodes.ConfigurationError;
        }
        stdout.WriteLine(report.Path);
        return ExitCodes.Ok;
    }

    private static bool HasState(StateSettings? state, TextWriter stderr)
    {
        if (state?.Path is { Length: > 0 }) return true;
        stderr.WriteLine("No Upload State is configured, so there is no Run History.");
        return false;
    }

    /// <summary>The value after <paramref name="flag"/>, or null when there is none (the next token is another flag).</summary>
    private static string? ValueOf(string[] args, string flag)
    {
        var index = Array.IndexOf(args, flag);
        return index >= 0 && index + 1 < args.Length && !args[index + 1].StartsWith("--", StringComparison.Ordinal) ? args[index + 1] : null;
    }

    public static string HelpText { get; } = """
        MIRES SFTP Uploader

        Usage: MiresSftpUploader [options]

        Options:
          --headless                Run once without opening a window.
          --list-runs [--limit N]   List the Runs in the Run History, newest first, then exit.
          --export-run <id>         Print the Report of a Run (or write it to --report), then exit.
          --report <path>           Write the Report of this Run (or of --export-run) to <path>:
                                    a file, or an existing directory to get the configured file name.
                                    Without it a Run writes its Report to the configured directory.
          --report-format json|csv  Format of the Report. Default: json.
          --version                 Print the version and exit.
          --help                    Print this help and exit.

        Exit codes:
          0    OK, or every file skipped as unchanged
          1    Some files failed
          2    Configuration or environment error
          3    Could not connect or authenticate (including host key mismatch)
          4    Another Run holds the lock
          130  Cancelled

        """;
}

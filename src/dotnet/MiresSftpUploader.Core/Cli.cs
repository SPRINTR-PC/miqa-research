namespace MiresSftpUploader.Core;

/// <summary>
/// The command-line surface that needs no window. Skeleton: <c>--version</c>, <c>--help</c>, and unknown-flag rejection.
/// stdout carries only the final result; diagnostics go to stderr.
/// </summary>
public static class Cli
{
    private static readonly string[] KnownFlags = ["--headless", "--version", "--help"];

    /// <summary>
    /// Handles the arguments when they ask for something that does not need the window.
    /// Returns false when the caller should go on to start the UI.
    /// </summary>
    public static bool TryRun(string[] args, string version, TextWriter stdout, TextWriter stderr, out int exitCode)
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

        return false;
    }

    public static string HelpText { get; } = """
        MIRES SFTP Uploader

        Usage: MiresSftpUploader [options]

        Options:
          --headless    Run once without opening a window.
          --version     Print the version and exit.
          --help        Print this help and exit.

        Exit codes:
          0    OK, or every file skipped as unchanged
          1    Some files failed
          2    Configuration or environment error
          3    Could not connect or authenticate (including host key mismatch)
          4    Another Run holds the lock
          130  Cancelled

        """;
}

namespace MiresSftpUploader.Core;

/// <summary>
/// The command-line surface that needs no window. Skeleton: <c>--version</c>, <c>--help</c>, and unknown-flag rejection.
/// stdout carries only the final result; diagnostics go to stderr.
/// </summary>
public static class Cli
{
    private static readonly string[] KnownFlags = ["--headless", "--version", "--help", "--init-data-dir", "--data-dir"];

    /// <summary>
    /// Handles the arguments when they ask for something that does not need the window.
    /// Returns false when the caller should go on to start the UI.
    /// </summary>
    public static bool TryRun(string[] args, string version, TextWriter stdout, TextWriter stderr, out int exitCode,
        Func<string, string?>? environment = null)
    {
        environment ??= Environment.GetEnvironmentVariable;
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

        if (args.Contains("--init-data-dir"))
        {
            exitCode = InitDataDirectory(args, stdout, stderr, environment);
            return true;
        }

        return false;
    }

    /// <summary>Creates or repairs the Data Directory (idempotent). Run once per machine by an administrator.</summary>
    private static int InitDataDirectory(string[] args, TextWriter stdout, TextWriter stderr, Func<string, string?> environment)
    {
        var index = Array.IndexOf(args, "--data-dir");
        var path = DataDirectory.Resolve(
            index >= 0 && index + 1 < args.Length ? args[index + 1] : null,
            environment(DataDirectory.EnvironmentVariable),
            DataDirectory.CurrentPlatform,
            Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData));
        var group = environment("State__AccessGroup");

        var result = DataDirectory.Initialize(path, string.IsNullOrWhiteSpace(group) ? null : group, DataDirectory.CurrentPlatform);
        foreach (var action in result.Actions) stdout.WriteLine(action);
        if (!result.Ok)
        {
            stderr.WriteLine(result.Error);
            return ExitCodes.ConfigurationError;
        }

        stdout.WriteLine(result.Actions.Count == 0 ? $"Data Directory {path} is already set up." : $"Data Directory {path} is ready.");
        return ExitCodes.Ok;
    }

    public static string HelpText { get; } = """
        MIRES SFTP Uploader

        Usage: MiresSftpUploader [options]

        Options:
          --headless    Run once without opening a window.
          --init-data-dir  Create or repair the shared Data Directory (run once per machine as
                        administrator or with sudo; safe to repeat). The group comes from
                        State__AccessGroup (default mires-uploader on Linux, staff on macOS).
          --data-dir <path>  Data Directory to use (default per OS; MIRES_DATA_DIR also works).
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

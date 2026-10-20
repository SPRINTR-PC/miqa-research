namespace MiresSftpUploader.Core;

/// <summary>
/// The command-line surface that needs no window. Answers <c>--version</c>, <c>--help</c>, <c>--validate-config</c>,
/// unknown flags and unknown <c>--source</c> names, and rejects an invalid configuration for a Headless Run.
/// stdout carries only the final result; diagnostics go to stderr.
/// </summary>
public static class Cli
{
    /// <summary>
    /// Handles the arguments when they ask for something that does not need the window.
    /// Returns false when the caller should go on (start the UI, or run the Headless Run).
    /// </summary>
    public static bool TryRun(string[] args, string version, TextWriter stdout, TextWriter stderr, out int exitCode, ConfigurationLocations? locations = null)
    {
        exitCode = ExitCodes.Ok;
        if (args.Length == 0) return false;

        var parsed = CliOptions.Parse(args);
        if (parsed.Options is not { } options)
        {
            stderr.WriteLine(parsed.Error);
            exitCode = ExitCodes.ConfigurationError;
            return true;
        }

        if (options.Version)
        {
            stdout.WriteLine(version);
            return true;
        }

        if (options.Help)
        {
            stdout.Write(HelpText);
            return true;
        }

        if (!options.Headless && !options.ValidateConfig) return false;

        var result = new Configuration(locations ?? ConfigurationLocations.Default()).Load(options, headless: true);
        var errors = result.Errors.Select(e => e.ToString()).ToList();
        if (result.Config is { } config)
            foreach (var name in options.Sources.Where(n => !config.Sources.Any(s => string.Equals(s.Name, n, StringComparison.OrdinalIgnoreCase))))
                errors.Add($"--source: unknown Source '{name}'. Configured Sources: {string.Join(", ", config.Sources.Select(s => s.Name))}.");

        foreach (var warning in result.Warnings)
            stderr.WriteLine($"warning: {warning}");
        if (errors.Count > 0)
        {
            stderr.WriteLine($"Configuration has {errors.Count} error(s):");
            foreach (var e in errors) stderr.WriteLine($"  {e}");
            exitCode = ExitCodes.ConfigurationError;
            return true;
        }

        if (!options.ValidateConfig) return false;
        stdout.WriteLine("Configuration is valid.");
        return true;
    }

    public static string HelpText { get; } = """
        MIRES SFTP Uploader

        Usage: MiresSftpUploader [options]

        Options:
          --headless              Run once without opening a window.
          --source <name>         Run only this Source; repeat for more. Default: every enabled Source.
          --dry-run               Plan only: upload, archive and record nothing.
          --rehash-all            Hash every file again instead of trusting the Upload State.
          --report <path>         Write a Report of the Run to this file.
          --report-format <f>     json (default) or csv.
          --export-run <id>       Export the Report of a recorded Run and exit.
          --list-runs             List recorded Runs and exit.
          --limit <n>             With --list-runs: show at most n Runs.
          --validate-config       Report every configuration error and exit; runs nothing.
          --check-connection      With --validate-config: also test the server and its host key.
          --init-data-dir         Create the shared Data Directory and exit.
          --log-level <level>     Trace, Debug, Info (default), Warn, Error or Fatal.
          --data-dir <path>       Use this Data Directory (also MIRES_DATA_DIR).
          --version               Print the version and exit.
          --help                  Print this help and exit.

        Settings come from, highest first: command-line flags, MIRES_* environment variables
        (MIRES_Sftp__Host, MIRES_Sources__0__Path), appsettings.user.json in the per-user
        application data folder, and appsettings.json next to the executable. A list is replaced
        whole by the highest layer that sets it. Secrets are read only from the environment:
        MIRES_SFTP_PASSWORD, MIRES_SFTP_KEY_PASSPHRASE, MIRES_S3_<SOURCE>_ACCESS_KEY and _SECRET_KEY.
        --list-runs, --export-run, --validate-config, --init-data-dir and --version imply --headless.

        Exit codes:
          0    OK, or every file skipped as unchanged
          1    Some files failed
          2    Configuration or environment error
          3    Could not connect or authenticate (including host key mismatch)
          4    Another Run holds the lock
          130  Cancelled

        """;
}

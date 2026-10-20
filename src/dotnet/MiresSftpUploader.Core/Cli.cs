using System.Globalization;

namespace MiresSftpUploader.Core;

/// <summary>
/// The command-line surface that needs no window. Answers <c>--version</c>, <c>--help</c>, <c>--validate-config</c>,
/// <c>--list-runs</c>, <c>--export-run</c>, unknown flags and unknown <c>--source</c> names, and rejects an invalid
/// configuration for a Headless Run.
/// stdout carries only the final result; diagnostics go to stderr.
/// </summary>
public static class Cli
{
    /// <summary>
    /// Handles the arguments when they ask for something that does not need the window.
    /// Returns false when the caller should go on (start the UI, or run the Headless Run).
    /// <paramref name="state"/> locates the Upload State for <c>--list-runs</c> and <c>--export-run</c>.
    /// </summary>
    public static bool TryRun(string[] args, string version, TextWriter stdout, TextWriter stderr, out int exitCode,
        ConfigurationLocations? locations = null, StateSettings? state = null, Func<SftpConnection, IRemote>? remoteFactory = null)
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

        if (options.InitDataDir)
        {
            exitCode = InitDataDirectory(options, new Configuration(locations ?? ConfigurationLocations.Default()), stdout, stderr);
            return true;
        }

        if (options.ListRuns || options.ExportRunId is not null)
        {
            exitCode = options.ListRuns ? ListRuns(options, stdout, stderr, state) : ExportRun(options, stdout, stderr, state, locations);
            return true;
        }

        if (!options.Headless && !options.ValidateConfig) return false;

        var configuration = new Configuration(locations ?? ConfigurationLocations.Default());
        var result = configuration.Load(options, headless: true);
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
        if (!options.CheckConnection)
        {
            stdout.WriteLine("Configuration is valid.");
            return true;
        }

        exitCode = CheckConnection(result.Config!.Sftp, configuration.LoadSecrets(), remoteFactory ?? (c => new SshNetRemote(c)), stdout, stderr);
        return true;
    }

    /// <summary>Opens one session to prove the server answers, the Host Key Fingerprint matches and the credentials work.</summary>
    private static int CheckConnection(SftpConfig sftp, Secrets secrets, Func<SftpConnection, IRemote> remoteFactory, TextWriter stdout, TextWriter stderr)
    {
        var missing = sftp.AuthMethod == AuthMethod.PrivateKey ? null : secrets.SftpPassword is null ? Secrets.SftpPasswordVariable : null;
        if (missing is not null)
        {
            stderr.WriteLine($"{missing} is not set. Secrets are read only from environment variables.");
            return ExitCodes.ConfigurationError;
        }

        var connection = SftpConnection.From(sftp, secrets);
        var connect = remoteFactory(connection).ConnectAsync(CancellationToken.None).GetAwaiter().GetResult();
        if (!connect.IsOk)
        {
            stderr.WriteLine($"Connection check failed for {connection}: {connect.Reason}");
            return ExitCodes.ConnectFailed;
        }

        connect.Value!.DisposeAsync().AsTask().GetAwaiter().GetResult();
        stdout.WriteLine($"Configuration is valid. Connected to {connection}; the host key matches the pinned Host Key Fingerprint.");
        return ExitCodes.Ok;
    }

    /// <summary>Creates or repairs the Data Directory (idempotent). Run once per machine by an administrator.</summary>
    private static int InitDataDirectory(CliOptions options, Configuration configuration, TextWriter stdout, TextWriter stderr)
    {
        var settings = configuration.ResolveDataDirectory(options);
        if (settings.Errors.Count > 0)
        {
            foreach (var e in settings.Errors) stderr.WriteLine(e.ToString());
            return ExitCodes.ConfigurationError;
        }

        var result = DataDirectory.Initialize(settings.Path, settings.AccessGroup, DataDirectory.CurrentPlatform);
        foreach (var action in result.Actions) stdout.WriteLine(action);
        if (!result.Ok)
        {
            stderr.WriteLine(result.Error);
            return ExitCodes.ConfigurationError;
        }

        stdout.WriteLine(result.Actions.Count == 0 ? $"Data Directory {settings.Path} is already set up." : $"Data Directory {settings.Path} is ready.");
        return ExitCodes.Ok;
    }

    private static int ListRuns(CliOptions options, TextWriter stdout, TextWriter stderr, StateSettings? state)
    {
        if (!HasState(state, stderr)) return ExitCodes.ConfigurationError;
        foreach (var run in new RunHistory(state!, TimeProvider.System).ListRuns(new RunFilter { Limit = options.Limit }))
        {
            var counts = string.Join(' ', run.Counts.OrderBy(kv => kv.Key, StringComparer.Ordinal).Select(kv => $"{kv.Key}={kv.Value}"));
            stdout.WriteLine(string.Join('\t', run.RunId, run.Status, run.ExitCode?.ToString(CultureInfo.InvariantCulture) ?? "-",
                run.StartedAt.ToString("O", CultureInfo.InvariantCulture), run.StartedBy, run.Mode, counts));
        }
        return ExitCodes.Ok;
    }

    /// <summary>Prints the Report of a recorded Run, or writes it to <c>--report</c> and prints that path.</summary>
    private static int ExportRun(CliOptions options, TextWriter stdout, TextWriter stderr, StateSettings? state, ConfigurationLocations? locations)
    {
        if (!Guid.TryParse(options.ExportRunId, out var runId))
        {
            stderr.WriteLine($"--export-run needs a Run id, not '{options.ExportRunId}'.");
            return ExitCodes.ConfigurationError;
        }

        ReportFormat format;
        if (options.ConfigOverrides.TryGetValue("Report:Format", out var requested))
        {
            if (!Enum.TryParse(requested, ignoreCase: true, out format) || !Enum.IsDefined(format))
            {
                stderr.WriteLine($"--report-format must be json or csv, not '{requested}'.");
                return ExitCodes.ConfigurationError;
            }
        }
        else
        {
            format = new Configuration(locations ?? ConfigurationLocations.Default()).Load(options, headless: true).Config?.Report.Format ?? ReportFormat.Json;
        }

        if (!HasState(state, stderr)) return ExitCodes.ConfigurationError;
        var text = new RunHistory(state!, TimeProvider.System).Export(runId, format);
        if (text is null)
        {
            stderr.WriteLine($"No Run {runId} in the Upload State.");
            return ExitCodes.ConfigurationError;
        }

        if (options.ReportPath is null)
        {
            stdout.Write(text);
            return ExitCodes.Ok;
        }
        try
        {
            ReportWriter.WriteFile(options.ReportPath, text);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            stderr.WriteLine($"Could not write the Report to {options.ReportPath}: {ex.Message}");
            return ExitCodes.ConfigurationError;
        }
        stdout.WriteLine(options.ReportPath);
        return ExitCodes.Ok;
    }

    private static bool HasState(StateSettings? state, TextWriter stderr)
    {
        if (state?.Path is { Length: > 0 }) return true;
        stderr.WriteLine("No Upload State is configured, so there is no Run History.");
        return false;
    }

    public static string HelpText { get; } = """
        MIRES SFTP Uploader

        Usage: MiresSftpUploader [options]

        Options:
          --headless              Run once without opening a window. Default: open the window.
          --source <name>         Run only this Source; repeat for more. Default: every enabled Source.
          --dry-run               Plan only: upload, archive and record nothing. Default: off.
          --rehash-all            Hash every file again instead of trusting the Upload State. Default: off.
          --report <path>         Write a Report of the Run to this file. Default: Report:Directory, or reports/
                                  in the Data Directory (a Dry Run writes none unless given).
          --report-format <f>     json or csv. Default: json (Report:Format).
          --export-run <id>       Export the Report of a recorded Run and exit. Default: print it; --report saves it.
          --list-runs             List recorded Runs and exit.
          --limit <n>             With --list-runs: show at most n Runs. Default: all.
          --validate-config       Report every configuration error and exit; runs nothing.
          --check-connection      With --validate-config: also test the server and its host key.
          --init-data-dir         Create or repair the shared Data Directory and exit.
                                  Run once per machine as administrator or with sudo; safe to repeat.
                                  The group is State:AccessGroup (default mires-uploader, macOS staff).
          --log-level <level>     Trace, Debug, Info (default), Warn, Error or Fatal.
          --data-dir <path>       Use this Data Directory (also MIRES_DATA_DIR). Default: Windows
                                  %ProgramData%\MiresSftpUploader, macOS /Users/Shared/MiresSftpUploader,
                                  Linux /var/lib/mires-sftp-uploader.
          --version               Print the version and exit.
          --help                  Print this help and exit.

        Settings come from, highest first: command-line flags, MIRES_* environment variables
        (MIRES_Sftp__Host, MIRES_Sources__0__Path), appsettings.user.json in the per-user
        application data folder, and appsettings.json next to the executable. A list is replaced
        whole by the highest layer that sets it. Secrets are read only from the environment:
        MIRES_SFTP_PASSWORD, MIRES_SFTP_KEY_PASSPHRASE, MIRES_S3_<SOURCE>_ACCESS_KEY and _SECRET_KEY.
        stdout carries only the final summary line; logs go to stderr and the log file.
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

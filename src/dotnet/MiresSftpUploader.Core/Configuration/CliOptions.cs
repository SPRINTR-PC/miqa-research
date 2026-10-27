namespace MiresSftpUploader.Core;

public sealed record CliParseResult(CliOptions? Options, string? Error);

/// <summary>The parsed command line. The flags that map to a setting also appear in <see cref="ConfigOverrides"/>, the top configuration layer.</summary>
public sealed record CliOptions
{
    public bool Headless { get; init; }
    public IReadOnlyList<string> Sources { get; init; } = [];
    public bool DryRun { get; init; }
    public string? ReportPath { get; init; }
    public string? ExportRunId { get; init; }
    public bool ListRuns { get; init; }
    public int? Limit { get; init; }
    public bool ValidateConfig { get; init; }
    public bool CheckConnection { get; init; }
    public bool InitDataDir { get; init; }
    public string? SetSecret { get; init; }
    public string? ClearSecret { get; init; }
    public bool ListSecrets { get; init; }
    public bool Version { get; init; }
    public bool Help { get; init; }

    /// <summary>Start the Settings TUI. A mode flag: only --data-dir and --log-level may accompany it.</summary>
    public bool Configure { get; init; }
    public IReadOnlyDictionary<string, string> ConfigOverrides { get; init; } = new Dictionary<string, string>();

    /// <summary>Flags that start a Headless Run (or an administrative command) without a window.</summary>
    public bool ImpliesHeadless => Headless || ListRuns || ExportRunId is not null || ValidateConfig || InitDataDir || Version || SetSecret is not null || ClearSecret is not null || ListSecrets || Configure;

    private static readonly HashSet<string> ValueFlags =
        ["--source", "--report", "--report-format", "--export-run", "--limit", "--log-level", "--data-dir", "--set-secret", "--clear-secret"];

    private static readonly HashSet<string> SwitchFlags =
        ["--headless", "--dry-run", "--rehash-all", "--list-runs", "--validate-config", "--check-connection", "--init-data-dir", "--list-secrets", "--version", "--help", "--configure"];

    public static CliParseResult Parse(IReadOnlyList<string> args)
    {
        var options = new CliOptions();
        var sources = new List<string>();
        var overrides = new Dictionary<string, string>();
        var seen = new List<string>();

        for (var i = 0; i < args.Count; i++)
        {
            var arg = args[i];
            string? inlineValue = null;
            var name = arg;
            var eq = arg.IndexOf('=');
            if (arg.StartsWith("--", StringComparison.Ordinal) && eq > 0)
            {
                name = arg[..eq];
                inlineValue = arg[(eq + 1)..];
            }

            if (arg.StartsWith("--", StringComparison.Ordinal)) seen.Add(name);
            if (SwitchFlags.Contains(name) && inlineValue is null)
            {
                options = name switch
                {
                    "--headless" => options with { Headless = true },
                    "--dry-run" => options with { DryRun = true },
                    "--rehash-all" => Override(options, overrides, "Upload:RehashAll", "true"),
                    "--list-runs" => options with { ListRuns = true },
                    "--validate-config" => options with { ValidateConfig = true },
                    "--check-connection" => options with { CheckConnection = true },
                    "--init-data-dir" => options with { InitDataDir = true },
                    "--list-secrets" => options with { ListSecrets = true },
                    "--version" => options with { Version = true },
                    "--configure" => options with { Configure = true },
                    _ => options with { Help = true },
                };
                continue;
            }

            // A bare argument is not echoed: it may be a Secret value typed where only a name belongs.
            if (!arg.StartsWith("--", StringComparison.Ordinal))
                return new(null, "Unexpected argument. Values are never given on the command line. Use --help to list the options.");
            if (!ValueFlags.Contains(name))
                return new(null, $"Unknown option '{name}'. Use --help to list the options.");

            var value = inlineValue;
            if (value is null)
            {
                if (i + 1 >= args.Count || args[i + 1].StartsWith("--", StringComparison.Ordinal))
                    return new(null, $"Option '{name}' needs a value.");
                value = args[++i];
            }

            switch (name)
            {
                case "--source": sources.Add(value); break;
                case "--report": options = options with { ReportPath = value }; break;
                case "--set-secret": options = options with { SetSecret = value }; break;
                case "--clear-secret": options = options with { ClearSecret = value }; break;
                case "--export-run": options = options with { ExportRunId = value }; break;
                case "--limit":
                    if (!int.TryParse(value, out var limit) || limit < 1)
                        return new(null, $"Option '--limit' needs a positive number, not '{value}'.");
                    options = options with { Limit = limit };
                    break;
                case "--report-format": options = Override(options, overrides, "Report:Format", value); break;
                case "--log-level": options = Override(options, overrides, "Logging:Level", value); break;
                case "--data-dir": options = Override(options, overrides, "State:Path", value); break;
            }
        }

        if (options.Configure && seen.FirstOrDefault(n => n is not ("--configure" or "--data-dir" or "--log-level")) is { } other)
            return new(null, $"--configure starts the Settings TUI and accepts only --data-dir and --log-level, not '{other}'.");

        return new(options with { Sources = sources, ConfigOverrides = overrides }, null);
    }

    private static CliOptions Override(CliOptions options, Dictionary<string, string> overrides, string key, string value)
    {
        overrides[key] = value;
        return options;
    }
}

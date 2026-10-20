namespace MiresSftpUploader.Core;

/// <summary>
/// A Headless Run: prepares the Engine, runs once and prints the one-line summary. stdout carries only that line;
/// configuration problems go to stderr. Needs no window and no display.
/// </summary>
public static class HeadlessRunner
{
    public static async Task<int> RunAsync(CliOptions cli, IUploaderRuntime runtime, TextWriter stdout, TextWriter stderr, CancellationToken cancellationToken)
    {
        var prepared = runtime.Prepare(headless: true);
        if (prepared.Config is not { } config || prepared.Engine is not { } engine)
        {
            stderr.WriteLine($"Configuration has {prepared.Errors.Count} error(s):");
            foreach (var error in prepared.Errors) stderr.WriteLine($"  {error}");
            return ExitCodes.ConfigurationError;
        }

        foreach (var warning in prepared.Warnings) stderr.WriteLine($"warning: {warning}");

        var options = new RunOptions
        {
            // The configured spelling, so a differently-cased --source still finds its Source.
            SourceNames = cli.Sources
                .Select(n => config.Sources.FirstOrDefault(s => string.Equals(s.Name, n, StringComparison.OrdinalIgnoreCase))?.Name ?? n)
                .ToList(),
            DryRun = cli.DryRun,
            RehashAll = config.Upload.RehashAll,
            Trigger = RunTrigger.Headless,
            ReportPath = cli.ReportPath,
        };

        var result = await engine.RunAsync(options, new Progress<RunEvent>(), cancellationToken);
        HeadlessSummary.Write(stdout, result, result.ReportPath);
        return result.ExitCode;
    }
}

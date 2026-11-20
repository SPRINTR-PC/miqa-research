using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

namespace MiresSftpUploader.Core;

/// <summary>
/// A Headless Run: prepares the Engine, runs once and prints the one-line summary. stdout carries only that line;
/// configuration problems go to stderr. Needs no window and no display.
/// </summary>
public static class HeadlessRunner
{
    public static async Task<int> RunAsync(CliOptions cli, IUploaderRuntime runtime, TextWriter stdout, TextWriter stderr, CancellationToken cancellationToken,
        StatusLineWriter? statusLine = null, ILoggerFactory? loggers = null, TimeProvider? time = null)
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

        var plans = new PlanCollector();
        RunResult result;
        using (var progress = new HeadlessProgress(statusLine, loggers ?? NullLoggerFactory.Instance, time ?? TimeProvider.System))
        {
            try
            {
                result = await engine.RunAsync(options, new Fanout(plans, progress), cancellationToken);
            }
            finally
            {
                // Before the summary, and on every way out, so no status line stays on the terminal.
                statusLine?.Clear();
            }
        }
        foreach (var plan in plans.Plans) stderr.WriteLine(Describe(plan));
        HeadlessSummary.Write(stdout, result, result.ReportPath);
        return result.ExitCode;
    }

    /// <summary>One line on stderr per zip Archive a Dry Run planned.</summary>
    private static string Describe(ArchivePlanned plan) =>
        $"archive: {plan.Source}/{plan.Name} rule={plan.Rule} files={plan.MemberCount} bytes={plan.TotalSize} status={plan.Status}";

    private sealed class Fanout(params IProgress<RunEvent>[] targets) : IProgress<RunEvent>
    {
        public void Report(RunEvent value)
        {
            foreach (var target in targets) target.Report(value);
        }
    }

    /// <summary>Keeps the Archive plans of a Dry Run; unlike <see cref="Progress{T}"/> it takes each event on the spot, so none is missing when the Run ends.</summary>
    private sealed class PlanCollector : IProgress<RunEvent>
    {
        private readonly List<ArchivePlanned> _plans = [];

        public IReadOnlyList<ArchivePlanned> Plans { get { lock (_plans) return _plans.ToList(); } }

        public void Report(RunEvent value)
        {
            if (value is ArchivePlanned plan) lock (_plans) _plans.Add(plan);
        }
    }
}

using System.Runtime.CompilerServices;
using System.Threading.Channels;
using MiresSftpUploader.Core;

namespace MiresSftpUploader.Test.Support;

/// <summary>An in-memory <see cref="IRunHistory"/> for view-model tests.</summary>
public sealed class FakeRunHistory : IRunHistory
{
    private readonly List<RunDetail> _runs = [];
    private readonly Dictionary<Guid, Channel<RunDetail>> _watches = [];

    public List<RunFilter> Filters { get; } = [];
    public List<Guid> CancelRequests { get; } = [];
    public List<(Guid RunId, ReportFormat Format)> Saved { get; } = [];
    public int SweepCount { get; private set; }

    /// <summary>Adds a Run; the order added is the order listed (newest first).</summary>
    public RunDetail Add(string status = "Finished", int? exitCode = 0, string startedBy = "anna", string mode = "Run",
        IReadOnlyDictionary<string, int>? counts = null, IReadOnlyList<RunFileOutcome>? files = null, bool cancelRequested = false,
        DateTimeOffset? startedAt = null, DateTimeOffset? endedAt = null, DateTimeOffset? heartbeat = null)
    {
        var started = startedAt ?? new DateTimeOffset(2026, 3, 1, 12, 0, 0, TimeSpan.Zero).AddMinutes(-_runs.Count * 10);
        var detail = new RunDetail(
            new RunSummary(Guid.NewGuid(), status, exitCode, startedBy, mode, "Ui", started,
                endedAt ?? (status == "Running" ? null : started.AddMinutes(3)), heartbeat ?? started, cancelRequested,
                counts ?? new Dictionary<string, int>()),
            files ?? [],
            (files ?? []).Where(f => f.Outcome == "Succeeded").Sum(f => f.Bytes));
        _runs.Add(detail);
        return detail;
    }

    public void Replace(RunDetail detail)
    {
        var i = _runs.FindIndex(r => r.Summary.RunId == detail.Summary.RunId);
        _runs[i] = detail;
    }

    /// <summary>Makes <see cref="WatchRun"/> yield this snapshot (and replaces the stored Run).</summary>
    public void Publish(RunDetail detail, bool complete = false)
    {
        Replace(detail);
        var channel = Watch(detail.Summary.RunId);
        channel.Writer.TryWrite(detail);
        if (complete) channel.Writer.TryComplete();
    }

    private Channel<RunDetail> Watch(Guid id) =>
        _watches.TryGetValue(id, out var c) ? c : _watches[id] = Channel.CreateUnbounded<RunDetail>();

    public IReadOnlyList<RunSummary> ListRuns(RunFilter? filter = null)
    {
        filter ??= new RunFilter();
        Filters.Add(filter);
        return _runs.Select(r => r.Summary).Where(s => filter.Kind switch
        {
            RunFilterKind.Live => s.Status == "Running",
            RunFilterKind.NeedsAttention => s.Status == "Abandoned" || (s.ExitCode is { } e && e != 0),
            _ => true,
        }).ToList();
    }

    public RunDetail? GetRun(Guid runId) => _runs.FirstOrDefault(r => r.Summary.RunId == runId);

    public string? Export(Guid runId, ReportFormat format) => GetRun(runId) is null ? null : $"report {runId} {format}";

    public string? SaveReport(Guid runId, ReportFormat format)
    {
        if (GetRun(runId) is null) return null;
        Saved.Add((runId, format));
        return $"/reports/run-{runId}.{(format == ReportFormat.Csv ? "csv" : "json")}";
    }

    public bool RequestCancel(Guid runId)
    {
        CancelRequests.Add(runId);
        var run = GetRun(runId);
        if (run is null || run.Summary.Status != "Running") return false;
        Replace(run with { Summary = run.Summary with { CancelRequested = true } });
        return true;
    }

    public int SweepAbandoned() => ++SweepCount;

    public async IAsyncEnumerable<RunDetail> WatchRun(Guid runId, [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        var channel = Watch(runId);
        while (await channel.Reader.WaitToReadAsync(cancellationToken).ConfigureAwait(false))
            while (channel.Reader.TryRead(out var detail))
                yield return detail;
    }
}

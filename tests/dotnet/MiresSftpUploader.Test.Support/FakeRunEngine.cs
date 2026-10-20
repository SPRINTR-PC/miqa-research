using MiresSftpUploader.Core;

namespace MiresSftpUploader.Test.Support;

/// <summary>
/// A scripted <see cref="IRunEngine"/> for view-model tests: reports the given events, then waits for
/// <see cref="Release"/> (or cancellation) before finishing with the given exit code.
/// </summary>
public sealed class FakeRunEngine : IRunEngine
{
    private readonly TaskCompletionSource _gate = new(TaskCreationOptions.RunContinuationsAsynchronously);
    private readonly TaskCompletionSource _started = new(TaskCreationOptions.RunContinuationsAsynchronously);

    public List<RunOptions> Calls { get; } = [];

    /// <summary>The events reported on the next Run, after <see cref="RunStarted"/>.</summary>
    public List<RunEvent> Script { get; } = [];

    public int ExitCode { get; set; }
    public string? Reason { get; set; }
    public Exception? Throw { get; set; }

    /// <summary>When true the Run does not finish until <see cref="Release"/> or cancellation.</summary>
    public bool Hold { get; set; }

    public Guid LastRunId { get; private set; }

    /// <summary>Completes once the Run has reported its events and is waiting.</summary>
    public Task Started => _started.Task;

    public void Release() => _gate.TrySetResult();

    public async Task<RunResult> RunAsync(RunOptions options, IProgress<RunEvent> progress, CancellationToken cancellationToken)
    {
        Calls.Add(options);
        LastRunId = Guid.NewGuid();
        if (Throw is not null) throw Throw;

        progress.Report(new RunStarted(LastRunId, DateTimeOffset.UnixEpoch));
        foreach (var e in Script) progress.Report(e);
        _started.TrySetResult();

        var exit = ExitCode;
        var reason = Reason;
        if (Hold)
        {
            try
            {
                await _gate.Task.WaitAsync(cancellationToken);
            }
            catch (OperationCanceledException)
            {
                exit = ExitCodes.Cancelled;
                reason = "Cancelled";
            }
        }

        var counts = Script.OfType<FileOutcomeChanged>()
            .GroupBy(e => (e.Source, e.RelativePath))
            .Select(g => g.Last())
            .GroupBy(e => e.Outcome)
            .ToDictionary(g => g.Key, g => g.Count());
        var result = new RunResult(LastRunId, counts, exit, reason);
        progress.Report(new RunFinished(result));
        return result;
    }
}

/// <summary>An <see cref="IUploaderRuntime"/> that returns a prepared configuration around a given engine.</summary>
public sealed class FakeUploaderRuntime(AppConfig? config, IRunEngine? engine, IReadOnlyList<ConfigError>? errors = null) : IUploaderRuntime
{
    public int PrepareCount { get; private set; }

    public PreparedUploader Prepare(bool headless)
    {
        PrepareCount++;
        return new PreparedUploader(config, errors ?? [], [], SecretStatus.None, engine);
    }
}

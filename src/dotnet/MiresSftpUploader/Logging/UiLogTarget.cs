using System;
using Microsoft.Extensions.Logging;
using NLog;
using LogLevel = Microsoft.Extensions.Logging.LogLevel;
using NLog.Targets;

namespace MiresSftpUploader.Logging;

/// <summary>One line for the log pane.</summary>
public sealed record LogEntry(DateTimeOffset Time, LogLevel Level, string Logger, string Message);

/// <summary>
/// An NLog target that hands each event to subscribers instead of writing it anywhere. The log pane subscribes;
/// it is registered in code (not by assembly scanning) so it also works when trimmed or published as a single file.
/// Called on whatever thread logged, so subscribers must not touch the UI directly.
/// </summary>
[Target("UiLog")]
public sealed class UiLogTarget : TargetWithLayout
{
    public UiLogTarget() => Layout = "${message}";

    public event Action<LogEntry>? LogReceived;

    protected override void Write(LogEventInfo logEvent)
    {
        if (LogReceived is null) return;
        Emit(new LogEntry(
            new DateTimeOffset(logEvent.TimeStamp),
            ToMicrosoft(logEvent.Level),
            logEvent.LoggerName ?? "",
            RenderLogEvent(Layout, logEvent)));
    }

    /// <summary>Hands an entry to the subscribers, as <see cref="Write"/> does for each log event.</summary>
    public void Emit(LogEntry entry) => LogReceived?.Invoke(entry);

    private static LogLevel ToMicrosoft(NLog.LogLevel level) =>
        level.Ordinal switch
        {
            0 => LogLevel.Trace,
            1 => LogLevel.Debug,
            2 => LogLevel.Information,
            3 => LogLevel.Warning,
            4 => LogLevel.Error,
            _ => LogLevel.Critical,
        };
}

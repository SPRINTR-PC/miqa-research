using Microsoft.Extensions.Logging;

namespace MiresSftpUploader.Test.Unit;

public sealed record CapturedLog(LogLevel Level, string Category, string Message);

/// <summary>Records every message a logger writes, as the formatted text a log file would hold.</summary>
public sealed class CapturingLoggerProvider : ILoggerProvider
{
    private readonly List<CapturedLog> _entries = [];

    public IReadOnlyList<CapturedLog> Entries
    {
        get { lock (_entries) return _entries.ToList(); }
    }

    public ILogger CreateLogger(string categoryName) => new CapturingLogger(this, categoryName);

    public void Dispose() { }

    private sealed class CapturingLogger(CapturingLoggerProvider owner, string category) : ILogger
    {
        public IDisposable? BeginScope<TState>(TState state) where TState : notnull => null;
        public bool IsEnabled(LogLevel logLevel) => true;

        public void Log<TState>(LogLevel logLevel, EventId eventId, TState state, Exception? exception, Func<TState, Exception?, string> formatter)
        {
            var text = formatter(state, exception);
            if (exception is not null) text += Environment.NewLine + exception;
            lock (owner._entries) owner._entries.Add(new CapturedLog(logLevel, category, text));
        }
    }
}

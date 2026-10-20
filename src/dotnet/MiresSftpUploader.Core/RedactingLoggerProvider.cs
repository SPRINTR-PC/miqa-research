using Microsoft.Extensions.Logging;

namespace MiresSftpUploader.Core;

/// <summary>
/// Wraps a logger provider so every message and exception is passed through the <see cref="Redactor"/> before it
/// reaches the inner provider. The inner provider then sees a plain, already-redacted message and no exception object.
/// </summary>
public sealed class RedactingLoggerProvider(ILoggerProvider inner, Redactor redactor) : ILoggerProvider, ISupportExternalScope
{
    public ILogger CreateLogger(string categoryName) => new RedactingLogger(inner.CreateLogger(categoryName), redactor);

    public void SetScopeProvider(IExternalScopeProvider scopeProvider) => (inner as ISupportExternalScope)?.SetScopeProvider(scopeProvider);

    public void Dispose() => inner.Dispose();

    private sealed class RedactingLogger(ILogger inner, Redactor redactor) : ILogger
    {
        public IDisposable? BeginScope<TState>(TState state) where TState : notnull => inner.BeginScope(state);

        public bool IsEnabled(LogLevel logLevel) => inner.IsEnabled(logLevel);

        public void Log<TState>(LogLevel logLevel, EventId eventId, TState state, Exception? exception, Func<TState, Exception?, string> formatter)
        {
            if (!inner.IsEnabled(logLevel)) return;
            var message = formatter(state, null);
            if (exception is not null) message += Environment.NewLine + exception;
            inner.Log(logLevel, eventId, redactor.Redact(message), null, static (text, _) => text);
        }
    }
}

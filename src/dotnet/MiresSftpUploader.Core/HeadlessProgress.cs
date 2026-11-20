using System.Globalization;
using System.Text;
using Microsoft.Extensions.Logging;

namespace MiresSftpUploader.Core;

/// <summary>
/// The Headless Run's progress consumer, alongside the plan collector: it counts the files that are done, redraws the
/// live status line on every <see cref="UploadProgress"/> snapshot (when there is a <see cref="StatusLineWriter"/>) and
/// logs one line every 10 s while files upload, under its own logger name (<see cref="LoggerName"/>) so a configuration
/// can keep it out of the stderr console target. A Scan or Dry Run emits no snapshot, so it shows and logs nothing.
/// </summary>
public sealed class HeadlessProgress : IProgress<RunEvent>, IDisposable
{
    /// <summary>The logger name of the 10 s progress lines; the generated logging configuration sends it to the log file only.</summary>
    public const string LoggerName = "MiresSftpUploader.Progress";

    /// <summary>Fixed: there is no setting for it.</summary>
    public static readonly TimeSpan LogInterval = TimeSpan.FromSeconds(10);

    private const double Mebibyte = 1024.0 * 1024.0;

    private readonly StatusLineWriter? _status;
    private readonly ILogger _log;
    private readonly ITimer _timer;
    private readonly object _gate = new();
    private readonly Dictionary<(string, string), FileOutcome> _files = [];
    private int _done;
    private int _ignored;
    private int _uploading;
    private double? _speed;

    public HeadlessProgress(StatusLineWriter? status, ILoggerFactory loggers, TimeProvider time)
    {
        _status = status;
        _log = loggers.CreateLogger(LoggerName);
        _timer = time.CreateTimer(_ => LogProgress(), null, LogInterval, LogInterval);
    }

    public void Report(RunEvent value)
    {
        switch (value)
        {
            case FileOutcomeChanged changed:
                lock (_gate) Count(changed);
                break;
            case UploadProgress snapshot:
                string text;
                lock (_gate)
                {
                    _uploading = snapshot.Files.Count;
                    _speed = snapshot.TotalUploadSpeed;
                    text = StatusText();
                }
                _status?.Set(text);
                break;
        }
    }

    private void Count(FileOutcomeChanged changed)
    {
        var key = (changed.Source, changed.RelativePath);
        if (_files.TryGetValue(key, out var before)) Adjust(before, -1);
        _files[key] = changed.Outcome;
        Adjust(changed.Outcome, +1);
    }

    private void Adjust(FileOutcome outcome, int by)
    {
        if (outcome is FileOutcome.Succeeded or FileOutcome.Failed or FileOutcome.Skipped) _done += by;
        else if (outcome == FileOutcome.Ignored) _ignored += by;
    }

    private int Total => _files.Count - _ignored;

    /// <summary>The status line: speed and uploading count are dropped when nothing uploads.</summary>
    private string StatusText()
    {
        var files = $"{_done.ToString("N0", CultureInfo.InvariantCulture)} of {Total.ToString("N0", CultureInfo.InvariantCulture)} files done";
        if (_uploading == 0) return files;
        var speed = _speed is { } s ? $"↑ {Format(s)} · " : "";
        return $"{speed}{_uploading.ToString(CultureInfo.InvariantCulture)} uploading · {files}";
    }

    private void LogProgress()
    {
        string message;
        lock (_gate)
        {
            if (_uploading == 0) return;
            var speed = _speed is { } s ? $", {Format(s)}" : "";
            message = $"progress: {_done.ToString("N0", CultureInfo.InvariantCulture)} of {Total.ToString("N0", CultureInfo.InvariantCulture)} files done, {_uploading.ToString(CultureInfo.InvariantCulture)} uploading{speed}";
        }
        _log.LogInformation("{Message}", message);
    }

    private static string Format(double bytesPerSecond) =>
        (bytesPerSecond / Mebibyte).ToString("F1", CultureInfo.InvariantCulture) + " MiB/s";

    public void Dispose() => _timer.Dispose();
}

/// <summary>
/// The one writer of stderr in an interactive Headless Run: it keeps one status line at the bottom, rewritten with a
/// carriage return and padding (no ANSI escapes, so it works on a Windows console too) and truncated to the window width.
/// Every other write (the log lines) clears the status line, goes through and redraws it, so a status line is never left
/// in front of a log line. <see cref="Clear"/> removes it for good: before the summary and on Ctrl+C.
/// </summary>
public sealed class StatusLineWriter(TextWriter inner, Func<int> width) : TextWriter
{
    private readonly object _gate = new();
    private string? _status;
    private int _drawn;
    private bool _atLineStart = true;
    private bool _closed;

    public override Encoding Encoding => inner.Encoding;

    /// <summary>Whether stderr is a terminal that can hold a status line: not redirected, <c>TERM</c> not <c>dumb</c>, <c>CI</c> not set.</summary>
    public static bool IsInteractive(bool errorRedirected, string? term, string? ci) =>
        !errorRedirected
        && !string.Equals(term, "dumb", StringComparison.OrdinalIgnoreCase)
        && string.IsNullOrEmpty(ci);

    public void Set(string text)
    {
        lock (_gate)
        {
            if (_closed) return;
            _status = text;
            if (_atLineStart) Draw();
        }
    }

    /// <summary>Erases the status line and keeps it from coming back.</summary>
    public void Clear()
    {
        lock (_gate)
        {
            _closed = true;
            _status = null;
            Erase();
            inner.Flush();
        }
    }

    public override void Write(char value) => Emit(value.ToString());
    public override void Write(string? value) => Emit(value);
    public override void Write(char[] buffer, int index, int count) => Emit(new string(buffer, index, count));
    public override void WriteLine(string? value) => Emit(value + NewLine);
    public override void WriteLine() => Emit(NewLine);
    public override void Flush() { lock (_gate) inner.Flush(); }

    private void Emit(string? text)
    {
        if (string.IsNullOrEmpty(text)) return;
        lock (_gate)
        {
            Erase();
            inner.Write(text);
            _atLineStart = text[^1] == '\n';
            if (_atLineStart) Draw();
            inner.Flush();
        }
    }

    private void Draw()
    {
        if (_status is null) return;
        var limit = Math.Max(1, width() - 1);
        var line = _status.Length > limit ? _status[..limit] : _status;
        inner.Write("\r" + line.PadRight(_drawn));
        _drawn = line.Length;
        inner.Flush();
    }

    private void Erase()
    {
        if (_drawn == 0) return;
        inner.Write("\r" + new string(' ', _drawn) + "\r");
        _drawn = 0;
    }
}

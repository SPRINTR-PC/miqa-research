using System.Text;

namespace MiresSftpUploader.Core;

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

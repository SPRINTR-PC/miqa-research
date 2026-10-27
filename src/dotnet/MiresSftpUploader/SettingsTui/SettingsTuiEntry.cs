using System;
using System.IO;
using MiresSftpUploader.Core;

namespace MiresSftpUploader.SettingsTui;

/// <summary>What the Settings TUI needs to know about the terminal it would take over. The seam that makes each refusal rule a unit test.</summary>
public interface ITerminalEnvironment
{
    bool IsInputRedirected { get; }
    bool IsOutputRedirected { get; }

    /// <summary>The <c>TERM</c> environment variable; null when unset.</summary>
    string? TermVariable { get; }

    /// <summary>Terminal size in cells; null when it cannot be read.</summary>
    int? WindowWidth { get; }

    int? WindowHeight { get; }
    bool IsWindows { get; }
}

/// <summary>The real terminal of the process.</summary>
public sealed class ConsoleTerminalEnvironment : ITerminalEnvironment
{
    public bool IsInputRedirected => Console.IsInputRedirected;
    public bool IsOutputRedirected => Console.IsOutputRedirected;
    public string? TermVariable => Environment.GetEnvironmentVariable("TERM");
    public int? WindowWidth => Read(() => Console.WindowWidth);
    public int? WindowHeight => Read(() => Console.WindowHeight);
    public bool IsWindows => OperatingSystem.IsWindows();

    private static int? Read(Func<int> size)
    {
        try { return size() is > 0 and var n ? n : null; }
        catch (Exception e) when (e is IOException or PlatformNotSupportedException) { return null; }
    }
}

/// <summary>The start of <c>--configure</c>: checks the terminal, then hands over to the Settings TUI.</summary>
public static class SettingsTuiEntry
{
    public const int MinimumWidth = 80;
    public const int MinimumHeight = 24;

    private const string Prefix = "--configure needs ";

    /// <summary>Why the Settings TUI cannot run here, or null when it can. One line, no line break.</summary>
    public static string? Refusal(ITerminalEnvironment terminal)
    {
        if (terminal.IsInputRedirected) return Prefix + "an interactive terminal, but stdin is redirected.";
        if (terminal.IsOutputRedirected) return Prefix + "an interactive terminal, but stdout is redirected.";
        if (!terminal.IsWindows && (string.IsNullOrEmpty(terminal.TermVariable) || terminal.TermVariable == "dumb"))
            return Prefix + "a terminal that supports full-screen output, but TERM is " + (string.IsNullOrEmpty(terminal.TermVariable) ? "not set." : "'dumb'.");
        if (terminal.WindowWidth is not { } width || terminal.WindowHeight is not { } height)
            return $"--configure could not read the terminal size; it needs at least {MinimumWidth}x{MinimumHeight}.";
        if (width < MinimumWidth || height < MinimumHeight)
            return $"{Prefix}a terminal of at least {MinimumWidth}x{MinimumHeight}, but it is {width}x{height}.";
        return null;
    }

    /// <summary>Refuses with exit code 2 (one stderr line; stdout is never written) or runs the Settings TUI and returns its exit code.</summary>
    /// <param name="run">Runs the Settings TUI; called only after every check passed, so before it initialises the terminal.</param>
    public static int Run(ITerminalEnvironment terminal, TextWriter stderr, Func<int> run)
    {
        if (Refusal(terminal) is { } refusal)
        {
            stderr.WriteLine(refusal);
            return ExitCodes.ConfigurationError;
        }

        return run();
    }
}

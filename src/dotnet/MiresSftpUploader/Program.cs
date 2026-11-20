using Avalonia;
using ReactiveUI.Avalonia;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using MiresSftpUploader.Core;
using MiresSftpUploader.Logging;
using MiresSftpUploader.SettingsTui;
using MiresSftpUploader.Tui;
using System;
using System.IO;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Threading;

namespace MiresSftpUploader;

sealed class Program
{
    // Initialization code. Don't use any Avalonia, third-party APIs or any
    // SynchronizationContext-reliant code before AppMain is called: things aren't initialized
    // yet and stuff might break.
    [STAThread]
    public static int Main(string[] args)
    {
        var options = CliOptions.Parse(args).Options;

        // Everything that needs no window is answered before Avalonia is built, so it works without a display.
        if (options?.ImpliesHeadless == true) WindowsConsole.Attach();

        var configuration = new Configuration(ConfigurationLocations.Default());
        var state = options is { ListRuns: true } or { ExportRunId: not null }
            ? UploaderComposition.LoadStateSettings(configuration, options)
            : null;
        if (Cli.TryRun(args, Version, Console.Out, Console.Error, out var exitCode, state: state, readSecret: ConsoleSecretInput.Read))
            return exitCode;

        if (options?.Configure == true)
            return SettingsTuiEntry.Run(new ConsoleTerminalEnvironment(), Console.Error, () => RunSettingsTui(configuration, options, ShellTab.Settings));

        if (options?.Tui == true)
            return SettingsTuiEntry.Run(new ConsoleTerminalEnvironment(), Console.Error, () => RunSettingsTui(configuration, options, ShellTab.Upload), "--tui");

        var headless = options?.Headless == true;
        // Before logging starts, so the stderr console target and the status line share one writer.
        var status = headless ? InteractiveStatusLine() : null;
        Logging = StartLogging(configuration, headless);
        try
        {
            var runtime = new UploaderRuntime(
                configuration,
                RemoteFactory,
                (ILoggerFactory?)Logging?.LoggerFactory ?? NullLoggerFactory.Instance,
                TimeProvider.System,
                options);

            if (headless)
                return RunHeadless(options!, runtime, status);

            AppHost.Current = new AppHost(configuration, runtime, Logging, options);
            return BuildAvaloniaApp().StartWithClassicDesktopLifetime(args);
        }
        finally
        {
            // Flush before returning so the last lines are not lost.
            Logging?.Dispose();
        }
    }

    /// <summary>The whole-app TUI (and --configure, which opens it on Settings): logs to the file only, so the terminal and stdout stay the interface's.</summary>
    private static int RunSettingsTui(Configuration configuration, CliOptions options, ShellTab start)
    {
        Logging = StartLogging(configuration, headless: true, fileOnly: true);
        try
        {
            return SettingsTuiApp.Run(configuration, options, (ILoggerFactory?)Logging?.LoggerFactory ?? NullLoggerFactory.Instance, start: start,
                logTarget: Logging?.Ui);
        }
        finally
        {
            Logging?.Dispose();
        }
    }

    /// <summary>The seam to the SFTP server for the window and the Headless Run alike.</summary>
    private static IRemoteFactory RemoteFactory => new SshNetRemoteFactory();

    /// <summary>The shared stderr writer with the live status line, installed as <see cref="Console.Error"/>; null unless stderr is an interactive terminal.</summary>
    private static StatusLineWriter? InteractiveStatusLine()
    {
        if (!StatusLineWriter.IsInteractive(Console.IsErrorRedirected, Environment.GetEnvironmentVariable("TERM"), Environment.GetEnvironmentVariable("CI")))
            return null;
        var status = new StatusLineWriter(Console.Error, () =>
        {
            try { return Console.WindowWidth; }
            catch (IOException) { return 80; }
        });
        Console.SetError(status);
        return status;
    }

    private static int RunHeadless(CliOptions options, IUploaderRuntime runtime, StatusLineWriter? status)
    {
        using var cancellation = new CancellationTokenSource();
        ConsoleCancelEventHandler onCancel = (_, e) =>
        {
            e.Cancel = true;
            status?.Clear();
            cancellation.Cancel();
        };
        Console.CancelKeyPress += onCancel;
        try
        {
            return HeadlessRunner.RunAsync(options, runtime, Console.Out, Console.Error, cancellation.Token,
                status, (ILoggerFactory?)Logging?.LoggerFactory ?? NullLoggerFactory.Instance, TimeProvider.System).GetAwaiter().GetResult();
        }
        finally
        {
            Console.CancelKeyPress -= onCancel;
        }
    }

    /// <summary>Logging for this process; null when the configuration could not be loaded (the UI then shows the errors).</summary>
    public static AppLogging? Logging { get; private set; }

    private static AppLogging? StartLogging(Configuration configuration, bool headless, bool fileOnly = false)
    {
        var load = configuration.Load(headless: headless);
        if (load.Config is not { } config) return null;
        return AppLogging.Start(
            config.Logging,
            load.Section("NLog"),
            headless,
            Redactor.From(configuration.LoadSecrets()),
            Path.Combine(ConfigurationLocations.UserDataDirectory(), "logs"),
            fileOnly);
    }

    private static string Version =>
        (typeof(Program).Assembly.GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion ?? "0.0.0")
        .Split('+')[0];

    // Avalonia configuration, don't remove; also used by visual designer.
    public static AppBuilder BuildAvaloniaApp()
        => AppBuilder.Configure<App>()
            .UsePlatformDetect()
#if DEBUG
            .WithDeveloperTools()
#endif
            .WithInterFont()
            .LogToTrace()
            .UseReactiveUI(_ => { });
}

/// <summary>The executable is a Windows GUI program, so a Headless Run attaches to the console of the terminal that started it.</summary>
static class WindowsConsole
{
    private const uint AttachParentProcess = 0xFFFFFFFF;

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool AttachConsole(uint processId);

    public static void Attach()
    {
        if (!OperatingSystem.IsWindows() || !AttachConsole(AttachParentProcess)) return;
        // The standard handles were invalid at startup; open them again now that a console is attached.
        Console.SetOut(new StreamWriter(Console.OpenStandardOutput()) { AutoFlush = true });
        Console.SetError(new StreamWriter(Console.OpenStandardError()) { AutoFlush = true });
    }
}

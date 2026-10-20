using Avalonia;
using ReactiveUI.Avalonia;
using MiresSftpUploader.Core;
using MiresSftpUploader.Logging;
using System;
using System.IO;
using System.Linq;
using System.Reflection;

namespace MiresSftpUploader;

sealed class Program
{
    // Initialization code. Don't use any Avalonia, third-party APIs or any
    // SynchronizationContext-reliant code before AppMain is called: things aren't initialized
    // yet and stuff might break.
    [STAThread]
    public static int Main(string[] args)
    {
        // Flags that need no window are answered before Avalonia is built, so they work without a display.
        if (Cli.TryRun(args, Version, Console.Out, Console.Error, out var exitCode))
            return exitCode;

        var headless = args.Contains("--headless");
        Logging = StartLogging(headless);
        try
        {
            return BuildAvaloniaApp().StartWithClassicDesktopLifetime(args);
        }
        finally
        {
            // Flush before returning so the last lines are not lost.
            Logging?.Dispose();
        }
    }

    /// <summary>Logging for this process; null when the configuration could not be loaded (the UI then shows the errors).</summary>
    public static AppLogging? Logging { get; private set; }

    private static AppLogging? StartLogging(bool headless)
    {
        var configuration = new Configuration(ConfigurationLocations.Default());
        var load = configuration.Load(headless: headless);
        if (load.Config is not { } config) return null;
        return AppLogging.Start(
            config.Logging,
            load.Section("NLog"),
            headless,
            Redactor.From(configuration.LoadSecrets()),
            Path.Combine(ConfigurationLocations.UserDataDirectory(), "logs"));
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
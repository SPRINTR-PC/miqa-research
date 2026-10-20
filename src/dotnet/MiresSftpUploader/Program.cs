using Avalonia;
using ReactiveUI.Avalonia;
using MiresSftpUploader.Core;
using System;
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

        return BuildAvaloniaApp().StartWithClassicDesktopLifetime(args);
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
            .UseReactiveUI();
}
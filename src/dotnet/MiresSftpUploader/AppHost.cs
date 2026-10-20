using System;
using Microsoft.Extensions.Logging;
using MiresSftpUploader.Core;
using MiresSftpUploader.Logging;
using MiresSftpUploader.ViewModels;

namespace MiresSftpUploader;

/// <summary>What the window needs from the process: configuration, the Engine runtime and logging. Builds the window's view-model.</summary>
public sealed class AppHost(Configuration configuration, IUploaderRuntime runtime, AppLogging? logging)
{
    /// <summary>The host of the running process; set by <c>Program</c> before Avalonia starts.</summary>
    public static AppHost? Current { get; set; }

    /// <param name="post">Runs an action on the UI thread: <c>Dispatcher.UIThread.Post</c> in the app.</param>
    public MainWindowViewModel CreateMainWindowViewModel(Action<Action> post)
    {
        var ui = runtime.Prepare(headless: false).Config?.Ui ?? new UiConfig();
        var upload = new UploadPageViewModel(runtime, post);
        var log = logging?.Ui is { } target ? new LogPaneViewModel(target, post, ToLogLevel(ui.LogLevel)) : null;
        return new MainWindowViewModel(upload, log, ui.Theme, theme => UserSettings.SaveTheme(configuration, theme));
    }

    private static LogLevel ToLogLevel(LogLevelSetting level) => level switch
    {
        LogLevelSetting.Trace => LogLevel.Trace,
        LogLevelSetting.Debug => LogLevel.Debug,
        LogLevelSetting.Info => LogLevel.Information,
        LogLevelSetting.Warn => LogLevel.Warning,
        LogLevelSetting.Error => LogLevel.Error,
        _ => LogLevel.Critical,
    };
}

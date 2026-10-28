using System;
using System.Reactive.Concurrency;
using System.Runtime.InteropServices;
using Microsoft.Extensions.Logging;
using MiresSftpUploader.Core;
using MiresSftpUploader.Tui;
using MiresSftpUploader.ViewModels;
using ReactiveUI.Builder;
using Terminal.Gui.App;

namespace MiresSftpUploader.SettingsTui;

/// <summary>The whole-app TUI (<c>--tui</c>) and its Settings shortcut (<c>--configure</c>). Only reached after <see cref="SettingsTuiEntry"/> has checked the terminal.</summary>
public static class SettingsTuiApp
{
    /// <summary>Runs the Settings TUI until the user quits or the session is dropped.</summary>
    /// <param name="application">
    /// The Terminal.Gui application to run on, already initialised. Null (the real terminal) creates and initialises one and ReactiveUI too;
    /// tests pass an application on the headless driver (ReactiveUI is then initialised by the test).
    /// </param>
    /// <param name="dialogs">The modal questions; null runs the real dialogs on <paramref name="application"/>.</param>
    /// <returns>The process exit code: 0, or 130 after SIGHUP or SIGTERM (nothing is saved then).</returns>
    public static int Run(Configuration configuration, CliOptions options, ILoggerFactory loggerFactory,
        IApplication? application = null, ITuiDialogs? dialogs = null, ShellTab start = ShellTab.Settings)
    {
        var log = loggerFactory.CreateLogger("SettingsTui");
        var owned = application is null;
        if (owned)
        {
            // Everything runs on the Terminal.Gui thread, so the immediate scheduler is the main-thread scheduler.
            RxAppBuilder.CreateReactiveUIBuilder().WithMainThreadScheduler(ImmediateScheduler.Instance).WithCoreServices().BuildApp();
            application = Application.Create();
            application.Init();
        }

        try
        {
            var page = new SettingsPageViewModel(configuration, cli: options);
            using var window = new TuiShell(application!, page, dialogs ?? new TerminalGuiDialogs(application!), start,
                help: new HelpPage(HelpPage.CreateViewModel(_ => { })));
            window.SettingsWindow.ConnectionChecker = token => ConnectionCheck.CheckSavedAsync(configuration, c => new SshNetRemote(c), token, options);
            window.SettingsWindow.Redact = text => Redactor.From(configuration.LoadSecrets()).Redact(text);
            using var hangup = Register(PosixSignal.SIGHUP, application!, window);
            using var terminate = Register(PosixSignal.SIGTERM, application!, window);
            log.LogInformation("TUI started on the {Page} page.", start);
            application!.Run(window);
            log.LogInformation("TUI exited with code {ExitCode}.", window.ExitCode);
            return window.ExitCode;
        }
        finally
        {
            if (owned) application!.Dispose();
        }
    }

    /// <summary>A dropped SSH session (SIGHUP) or a stop request (SIGTERM) ends the TUI with exit code 130 and writes nothing.</summary>
    private static PosixSignalRegistration Register(PosixSignal signal, IApplication application, TuiShell window) =>
        PosixSignalRegistration.Create(signal, context =>
        {
            context.Cancel = true;
            application.Invoke(window.Terminate);
        });
}

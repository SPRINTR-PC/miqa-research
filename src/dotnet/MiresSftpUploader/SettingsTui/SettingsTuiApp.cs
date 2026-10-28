using System;
using System.Reactive.Concurrency;
using System.Runtime.InteropServices;
using Microsoft.Extensions.Logging;
using MiresSftpUploader.Core;
using MiresSftpUploader.Logging;
using ReactiveUI;
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
    /// <param name="runtime">The Engine runtime behind the Upload page; null builds the real one (SSH.NET remotes).</param>
    /// <param name="logTarget">The in-process log target for the Log pane; null leaves the pane empty.</param>
    /// <param name="shutdownSignals">
    /// The shutdown seam: registers the action to call on SIGHUP or SIGTERM (a second call exits at once) and returns what unregisters it.
    /// Null registers the real signals; tests pass their own and call the action.
    /// </param>
    /// <returns>The process exit code: 0, or 130 after SIGHUP or SIGTERM (nothing is saved then).</returns>
    public static int Run(Configuration configuration, CliOptions options, ILoggerFactory loggerFactory,
        IApplication? application = null, ITuiDialogs? dialogs = null, ShellTab start = ShellTab.Settings,
        IUploaderRuntime? runtime = null, UiLogTarget? logTarget = null, Func<Action, IDisposable>? shutdownSignals = null)
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
            var tuiDialogs = dialogs ?? new TerminalGuiDialogs(application!);
            runtime ??= new UploaderRuntime(configuration, new SshNetRemoteFactory(), loggerFactory, TimeProvider.System, options);
            var upload = new UploadPageViewModel(runtime, action => application!.Invoke(action), RunTrigger.Tui);
            page.WhenAnyValue(x => x.DataDirectoryProblem).Subscribe(problem => upload.BlockedReason = problem);
            page.Saved += upload.Refresh;
            var logLevel = AppHost.ToLogLevel(runtime.Prepare(headless: true).Config?.Ui.LogLevel ?? LogLevelSetting.Info);
            var logPane = logTarget is null ? null : new LogPaneViewModel(logTarget, action => application!.Invoke(action), logLevel);
            using var uploadPage = new UploadTuiPage(application!, upload, logPane, tuiDialogs);
            using var window = new TuiShell(application!, page, tuiDialogs, start, uploadPage,
                help: new HelpPage(HelpPage.CreateViewModel(_ => { })));
            window.SettingsWindow.ConnectionChecker = token => ConnectionCheck.CheckSavedAsync(configuration, c => new SshNetRemote(c), token, options);
            window.SettingsWindow.Redact = text => Redactor.From(configuration.LoadSecrets()).Redact(text);
            using var signals = (shutdownSignals ?? RegisterSignals(application!))(window.Terminate);
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
    private static Func<Action, IDisposable> RegisterSignals(IApplication application) => terminate =>
    {
        void Handle(PosixSignalContext context)
        {
            context.Cancel = true;
            try { application.Invoke(terminate); }
            catch (Exception) { /* already shut down */ }
        }

        return new Registrations(PosixSignalRegistration.Create(PosixSignal.SIGHUP, Handle), PosixSignalRegistration.Create(PosixSignal.SIGTERM, Handle));
    };

    private sealed class Registrations(params IDisposable[] items) : IDisposable
    {
        public void Dispose()
        {
            foreach (var item in items) item.Dispose();
        }
    }
}

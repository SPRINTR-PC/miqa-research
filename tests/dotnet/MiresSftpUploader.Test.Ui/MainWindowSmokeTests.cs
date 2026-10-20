using System;
using System.Collections.Generic;
using System.Linq;
using System.Reactive.Threading.Tasks;
using System.Threading.Tasks;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Headless;
using Avalonia.Headless.XUnit;
using Avalonia.Media;
using Avalonia.Styling;
using Avalonia.Threading;
using Avalonia.VisualTree;
using Microsoft.Extensions.Logging;
using MiresSftpUploader;
using MiresSftpUploader.Core;
using MiresSftpUploader.Logging;
using MiresSftpUploader.Test.Support;
using MiresSftpUploader.ViewModels;
using MiresSftpUploader.Views;
using ReactiveUI.Avalonia;
using Xunit;

[assembly: AvaloniaTestApplication(typeof(MiresSftpUploader.Test.Ui.TestAppBuilder))]

namespace MiresSftpUploader.Test.Ui;

public static class TestAppBuilder
{
    public static AppBuilder BuildAvaloniaApp() =>
        AppBuilder.Configure<App>().UseHeadless(new AvaloniaHeadlessPlatformOptions()).UseReactiveUI(_ => { });
}

public class MainWindowSmokeTests
{
    private static readonly AppConfig Config = new()
    {
        Sftp = new SftpConfig { Host = "sftp.mires.example" },
        Sources = [new SourceConfig { Name = "wsi", Path = "/data/wsi" }, new SourceConfig { Name = "dicom", Path = "/data/dicom" }],
    };

    private static (MainWindow Window, MainWindowViewModel Vm, FakeRunEngine Engine) Create(UiTheme theme = UiTheme.Dark, UiLogTarget? logTarget = null)
    {
        var engine = new FakeRunEngine();
        var post = new Action<Action>(a => a());
        var upload = new UploadPageViewModel(new FakeUploaderRuntime(Config, engine), post);
        var log = logTarget is null ? null : new LogPaneViewModel(logTarget, post, LogLevel.Information);
        var vm = new MainWindowViewModel(upload, log, theme, _ => null);
        var window = new MainWindow { DataContext = vm };
        return (window, vm, engine);
    }

    private static T Find<T>(Control root, string name) where T : Control =>
        root.GetVisualDescendants().OfType<T>().First(c => c.Name == name);

    [AvaloniaTheory]
    [InlineData(UiTheme.Dark)]
    [InlineData(UiTheme.Light)]
    public void The_window_constructs_and_shows_in_both_themes(UiTheme theme)
    {
        var (window, _, _) = Create(theme);

        window.Show();

        Assert.True(window.IsVisible);
        Assert.Equal(theme == UiTheme.Dark ? ThemeVariant.Dark : ThemeVariant.Light, Application.Current!.RequestedThemeVariant);
    }

    [AvaloniaFact]
    public void The_theme_toggle_switches_the_application_theme()
    {
        var (window, vm, _) = Create(UiTheme.Dark);
        window.Show();

        vm.ToggleThemeCommand.Execute().Subscribe();

        Assert.Equal(ThemeVariant.Light, Application.Current!.RequestedThemeVariant);
    }

    [AvaloniaTheory]
    [InlineData("Dark")]
    [InlineData("Light")]
    public void The_primary_button_text_is_readable_in_each_theme(string variant)
    {
        var theme = variant == "Dark" ? ThemeVariant.Dark : ThemeVariant.Light;
        var app = Application.Current!;
        Assert.True(app.TryGetResource("MPrimary", theme, out var background));
        Assert.True(app.TryGetResource("MPrimaryFg", theme, out var foreground));

        var ratio = Contrast(((ISolidColorBrush)background!).Color, ((ISolidColorBrush)foreground!).Color);

        Assert.True(ratio >= 4.5, $"contrast {ratio:0.0} in {variant}");
    }

    [AvaloniaFact]
    public void Every_theme_defines_the_same_brushes()
    {
        var app = Application.Current!;
        foreach (var key in new[] { "MBackground", "MForeground", "MCard", "MPrimary", "MPrimaryFg", "MBorder", "MSunken", "MSuccess", "MDestructive", "MInfo", "MMuted" })
            foreach (var theme in new[] { ThemeVariant.Dark, ThemeVariant.Light })
                Assert.True(app.TryGetResource(key, theme, out _), $"{key} missing in {theme}");
    }

    [AvaloniaFact]
    public void The_sidebar_has_the_logo_Sources_Destination_and_the_Run_controls()
    {
        var (window, _, _) = Create();
        window.Show();

        Assert.NotEmpty(window.GetVisualDescendants().OfType<MiresLogo>());
        var texts = window.GetVisualDescendants().OfType<TextBlock>().Select(t => t.Text).ToList();
        Assert.Contains("MIRES SFTP Uploader", texts);
        Assert.Contains("wsi", window.GetVisualDescendants().OfType<CheckBox>().Select(c => c.Content as string));
        Assert.Contains("sftp.mires.example:22", texts);
        foreach (var name in new[] { "StartButton", "DryRunButton", "ScanButton", "CancelButton", "ThemeButton", "SettingsButton", "HelpButton" })
            Assert.NotNull(Find<Button>(window, name));
    }

    [AvaloniaFact]
    public void The_four_tiles_follow_the_Run()
    {
        var (window, vm, engine) = Create();
        engine.Script.Add(new FileOutcomeChanged("wsi", "a", FileOutcome.Succeeded, null));
        engine.Script.Add(new FileOutcomeChanged("wsi", "b", FileOutcome.Failed, "x"));
        window.Show();

        vm.Upload.StartCommand.Execute().Subscribe();

        Assert.Equal("1", Find<TextBlock>(window, "SucceededTile").Text);
        Assert.Equal("1", Find<TextBlock>(window, "FailedTile").Text);
        Assert.Equal("0", Find<TextBlock>(window, "SkippedTile").Text);
        Assert.Equal("0", Find<TextBlock>(window, "PendingTile").Text);
    }

    [AvaloniaFact]
    public async Task Cancel_and_Retry_failed_buttons_are_enabled_only_when_they_apply()
    {
        var (window, vm, engine) = Create();
        engine.Hold = true;
        engine.ExitCode = ExitCodes.SomeFilesFailed;
        engine.Script.Add(new FileOutcomeChanged("wsi", "b", FileOutcome.Failed, "x"));
        window.Show();
        var start = Find<Button>(window, "StartButton");
        var cancel = Find<Button>(window, "CancelButton");
        var retry = Find<Button>(window, "RetryButton");

        Assert.True(start.IsEffectivelyEnabled);
        Assert.False(cancel.IsEffectivelyEnabled);
        Assert.False(retry.IsEffectivelyEnabled);

        var running = vm.Upload.StartCommand.Execute().ToTask();
        await engine.Started;
        Dispatcher.UIThread.RunJobs();
        Assert.False(start.IsEffectivelyEnabled);
        Assert.True(cancel.IsEffectivelyEnabled);
        Assert.False(retry.IsEffectivelyEnabled);

        engine.Release();
        await running;
        Dispatcher.UIThread.RunJobs();
        Assert.True(start.IsEffectivelyEnabled);
        Assert.False(cancel.IsEffectivelyEnabled);
        Assert.True(retry.IsEffectivelyEnabled);
    }

    [AvaloniaFact]
    public void The_log_pane_is_in_the_window_only_when_there_is_a_log_target()
    {
        var (without, _, _) = Create();
        without.Show();
        var (with, _, _) = Create(logTarget: new UiLogTarget());
        with.Show();

        Assert.False(Find<Expander>(without, "LogExpander").IsVisible);
        Assert.True(Find<Expander>(with, "LogExpander").IsVisible);
    }

    [AvaloniaFact]
    public void Log_lines_appear_in_the_pane()
    {
        var target = new UiLogTarget();
        var (window, _, _) = Create(logTarget: target);
        window.Show();
        Find<Expander>(window, "LogExpander").IsExpanded = true;

        target.Emit(new LogEntry(DateTimeOffset.UnixEpoch, LogLevel.Warning, "Test", "disk almost full"));
        Dispatcher.UIThread.RunJobs();
        window.UpdateLayout();

        Assert.Contains("disk almost full", window.GetVisualDescendants().OfType<TextBlock>().Select(t => t.Text));
    }

    [AvaloniaFact]
    public void Settings_and_Help_switch_the_main_area()
    {
        var (window, vm, _) = Create();
        window.Show();

        vm.ShowSettingsCommand.Execute().Subscribe();
        Assert.True(Find<Control>(window, "SettingsPage").IsVisible);
        Assert.False(Find<Control>(window, "UploadPage").IsVisible);
        vm.ShowHelpCommand.Execute().Subscribe();
        Assert.True(Find<Control>(window, "HelpPage").IsVisible);
    }

    private static double Contrast(Color a, Color b)
    {
        static double Channel(byte v)
        {
            var s = v / 255.0;
            return s <= 0.03928 ? s / 12.92 : Math.Pow((s + 0.055) / 1.055, 2.4);
        }
        static double Luminance(Color c) => 0.2126 * Channel(c.R) + 0.7152 * Channel(c.G) + 0.0722 * Channel(c.B);
        var (hi, lo) = (Math.Max(Luminance(a), Luminance(b)), Math.Min(Luminance(a), Luminance(b)));
        return (hi + 0.05) / (lo + 0.05);
    }
}

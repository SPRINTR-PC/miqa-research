using System;
using System.Reactive;
using MiresSftpUploader.Core;
using ReactiveUI;

namespace MiresSftpUploader.ViewModels;

public enum AppPage { Upload, Settings, Help }

/// <summary>
/// The window: the sidebar (navigation, theme), the page shown in the main area, and the log pane. The Upload page
/// owns the Sources and the Run controls.
/// </summary>
public sealed class MainWindowViewModel : ViewModelBase
{
    private readonly Func<UiTheme, string?> _saveTheme;
    private UiTheme _theme;
    private bool _systemIsDark = true;
    private AppPage _page = AppPage.Upload;
    private string _themeNotice = "";

    /// <param name="log">Null when there is no log target (the configuration could not be loaded).</param>
    /// <param name="saveTheme">Saves the theme to User Overrides; returns null, or why it could not be saved.</param>
    public MainWindowViewModel(UploadPageViewModel upload, LogPaneViewModel? log, UiTheme theme, Func<UiTheme, string?> saveTheme)
    {
        Upload = upload;
        Log = log;
        _theme = theme;
        _saveTheme = saveTheme;

        ToggleThemeCommand = ReactiveCommand.Create(ToggleTheme);
        ShowUploadCommand = ReactiveCommand.Create(() => { Page = AppPage.Upload; });
        ShowSettingsCommand = ReactiveCommand.Create(() => { Page = AppPage.Settings; });
        ShowHelpCommand = ReactiveCommand.Create(() => { Page = AppPage.Help; });
    }

    public UploadPageViewModel Upload { get; }
    public LogPaneViewModel? Log { get; }
    public bool HasLog => Log is not null;

    public ReactiveCommand<Unit, Unit> ToggleThemeCommand { get; }
    public ReactiveCommand<Unit, Unit> ShowUploadCommand { get; }
    public ReactiveCommand<Unit, Unit> ShowSettingsCommand { get; }
    public ReactiveCommand<Unit, Unit> ShowHelpCommand { get; }

    public AppPage Page
    {
        get => _page;
        private set
        {
            this.RaiseAndSetIfChanged(ref _page, value);
            this.RaisePropertyChanged(nameof(IsUploadPage));
            this.RaisePropertyChanged(nameof(IsSettingsPage));
            this.RaisePropertyChanged(nameof(IsHelpPage));
        }
    }

    public bool IsUploadPage => Page == AppPage.Upload;
    public bool IsSettingsPage => Page == AppPage.Settings;
    public bool IsHelpPage => Page == AppPage.Help;

    public UiTheme Theme
    {
        get => _theme;
        private set
        {
            this.RaiseAndSetIfChanged(ref _theme, value);
            RaiseThemeChanged();
        }
    }

    /// <summary>What <see cref="UiTheme.System"/> currently resolves to; set by the view from the operating system's theme.</summary>
    public bool SystemIsDark
    {
        get => _systemIsDark;
        set
        {
            this.RaiseAndSetIfChanged(ref _systemIsDark, value);
            RaiseThemeChanged();
        }
    }

    public bool IsDark => Theme == UiTheme.Dark || (Theme == UiTheme.System && SystemIsDark);

    /// <summary>Names the theme the button switches to.</summary>
    public string ThemeToggleLabel => IsDark ? "Light theme" : "Dark theme";

    /// <summary>Why the theme was not saved (a Locked Setting, for example); empty when it was.</summary>
    public string ThemeNotice
    {
        get => _themeNotice;
        private set => this.RaiseAndSetIfChanged(ref _themeNotice, value);
    }

    private void ToggleTheme()
    {
        Theme = IsDark ? UiTheme.Light : UiTheme.Dark;
        ThemeNotice = _saveTheme(Theme) is { } why ? $"The theme was not saved: {why}" : "";
    }

    private void RaiseThemeChanged()
    {
        this.RaisePropertyChanged(nameof(IsDark));
        this.RaisePropertyChanged(nameof(ThemeToggleLabel));
    }
}

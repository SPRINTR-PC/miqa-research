using System;
using System.Reactive;
using System.Threading.Tasks;
using MiresSftpUploader.Core;
using ReactiveUI;

namespace MiresSftpUploader.ViewModels;

public enum AppPage { Upload, History, Settings, Help }

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
    /// <param name="history">Null when there is no Run History to show.</param>
    /// <param name="settings">Null only in tests that do not need the Settings page.</param>
    public MainWindowViewModel(UploadPageViewModel upload, LogPaneViewModel? log, UiTheme theme, Func<UiTheme, string?> saveTheme,
        HistoryPageViewModel? history = null, SettingsPageViewModel? settings = null)
    {
        Settings = settings;
        settings?.WhenAnyValue(x => x.DataDirectoryProblem).Subscribe(problem => upload.BlockedReason = problem);
        if (settings is not null)
            settings.Saved += () =>
            {
                upload.Refresh();
                if (Enum.TryParse<UiTheme>(settings.Field("Ui:Theme").Value, out var saved)) Theme = saved;
            };
        Upload = upload;
        History = history;
        Log = log;
        _theme = theme;
        _saveTheme = saveTheme;

        ToggleThemeCommand = ReactiveCommand.Create(ToggleTheme);
        ShowUploadCommand = ReactiveCommand.Create(() => { Page = AppPage.Upload; });
        ShowHistoryCommand = ReactiveCommand.Create(() =>
        {
            History?.Refresh();
            Page = AppPage.History;
        });
        ShowSettingsCommand = ReactiveCommand.Create(() => { Page = AppPage.Settings; });
        ShowHelpCommand = ReactiveCommand.Create(() => { Page = AppPage.Help; });
    }

    public UploadPageViewModel Upload { get; }
    public HistoryPageViewModel? History { get; }
    public LogPaneViewModel? Log { get; }

    /// <summary>The Settings page; null only in tests that do not need it.</summary>
    public SettingsPageViewModel? Settings { get; }
    public bool HasLog => Log is not null;

    public ReactiveCommand<Unit, Unit> ToggleThemeCommand { get; }
    public ReactiveCommand<Unit, Unit> ShowUploadCommand { get; }
    public ReactiveCommand<Unit, Unit> ShowHistoryCommand { get; }
    public ReactiveCommand<Unit, Unit> ShowSettingsCommand { get; }
    public ReactiveCommand<Unit, Unit> ShowHelpCommand { get; }

    public AppPage Page
    {
        get => _page;
        private set
        {
            this.RaiseAndSetIfChanged(ref _page, value);
            this.RaisePropertyChanged(nameof(IsUploadPage));
            this.RaisePropertyChanged(nameof(IsHistoryPage));
            this.RaisePropertyChanged(nameof(IsSettingsPage));
            this.RaisePropertyChanged(nameof(IsHelpPage));
        }
    }

    public bool IsUploadPage => Page == AppPage.Upload;
    public bool IsHistoryPage => Page == AppPage.History;
    public bool IsSettingsPage => Page == AppPage.Settings;
    public bool IsHelpPage => Page == AppPage.Help;

    /// <summary>Retry from the History page: shows the Upload page, where the new Run is followed.</summary>
    public Task RetryFromHistoryAsync(Guid runId)
    {
        Page = AppPage.Upload;
        return Upload.RetryRunAsync(runId);
    }

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
        private set
        {
            this.RaiseAndSetIfChanged(ref _themeNotice, value);
            this.RaisePropertyChanged(nameof(HasThemeNotice));
        }
    }

    public bool HasThemeNotice => ThemeNotice.Length > 0;

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

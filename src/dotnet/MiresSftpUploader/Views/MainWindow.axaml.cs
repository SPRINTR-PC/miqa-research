using System.ComponentModel;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Styling;
using MiresSftpUploader.Core;
using MiresSftpUploader.ViewModels;

namespace MiresSftpUploader.Views;

public partial class MainWindow : Window
{
    public MainWindow()
    {
        InitializeComponent();
        DataContextChanged += (_, _) => Attach();
        ActualThemeVariantChanged += (_, _) => ReportSystemTheme();
    }

    private MainWindowViewModel? _vm;

    private void Attach()
    {
        if (_vm is not null) _vm.PropertyChanged -= OnViewModelChanged;
        _vm = DataContext as MainWindowViewModel;
        if (_vm is null) return;
        _vm.PropertyChanged += OnViewModelChanged;
        ApplyTheme();
    }

    private void OnViewModelChanged(object? sender, PropertyChangedEventArgs e)
    {
        if (e.PropertyName == nameof(MainWindowViewModel.Theme)) ApplyTheme();
    }

    private void ApplyTheme()
    {
        if (_vm is null) return;
        var variant = _vm.Theme switch
        {
            UiTheme.Light => ThemeVariant.Light,
            UiTheme.Dark => ThemeVariant.Dark,
            _ => ThemeVariant.Default,
        };
        if (Application.Current is { } app) app.RequestedThemeVariant = variant;
        RequestedThemeVariant = variant;
        ReportSystemTheme();
    }

    private void ReportSystemTheme()
    {
        if (_vm is { Theme: UiTheme.System })
            _vm.SystemIsDark = ActualThemeVariant == ThemeVariant.Dark;
    }
}

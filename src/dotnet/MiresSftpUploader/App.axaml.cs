using Avalonia;
using Avalonia.Controls.ApplicationLifetimes;
using Avalonia.Markup.Xaml;
using Avalonia.Threading;
using MiresSftpUploader.Views;

namespace MiresSftpUploader;

public partial class App : Application
{
    public override void Initialize()
    {
        AvaloniaXamlLoader.Load(this);
    }

    public override void OnFrameworkInitializationCompleted()
    {
        if (ApplicationLifetime is IClassicDesktopStyleApplicationLifetime desktop && AppHost.Current is { } host)
        {
            desktop.MainWindow = new MainWindow
            {
                DataContext = host.CreateMainWindowViewModel(action => Dispatcher.UIThread.Post(action)),
            };
        }

        base.OnFrameworkInitializationCompleted();
    }
}

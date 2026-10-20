using Avalonia;
using Avalonia.Controls.ApplicationLifetimes;
using Avalonia.Markup.Xaml;
using MiresSftpUploader.ViewModels;
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
        if (ApplicationLifetime is IClassicDesktopStyleApplicationLifetime desktop)
        {
            desktop.MainWindow = new MainWindow
            {
                DataContext = new MiresSftpUploader.Prototype.ProtoVm(),
            };
        }

        base.OnFrameworkInitializationCompleted();
    }
}
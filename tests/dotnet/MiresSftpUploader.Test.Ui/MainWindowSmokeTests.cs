using Avalonia;
using Xunit;
using Avalonia.Headless;
using Avalonia.Headless.XUnit;
using MiresSftpUploader;
using MiresSftpUploader.Views;

[assembly: AvaloniaTestApplication(typeof(MiresSftpUploader.Test.Ui.TestAppBuilder))]

namespace MiresSftpUploader.Test.Ui;

public static class TestAppBuilder
{
    public static AppBuilder BuildAvaloniaApp() =>
        AppBuilder.Configure<App>().UseHeadless(new AvaloniaHeadlessPlatformOptions());
}

public class MainWindowSmokeTests
{
    [AvaloniaFact]
    public void Main_window_constructs_and_shows()
    {
        var window = new MainWindow();

        window.Show();

        Assert.True(window.IsVisible);
    }
}

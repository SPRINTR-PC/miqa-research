using System;
using System.Linq;
using Avalonia.Controls;
using Avalonia.Headless.XUnit;
using Avalonia.VisualTree;
using Markdown.Avalonia;
using MiresSftpUploader.Core;
using MiresSftpUploader.Test.Support;
using MiresSftpUploader.ViewModels;
using MiresSftpUploader.Views;
using Xunit;

namespace MiresSftpUploader.Test.Ui;

public class HelpPageTests
{
    [AvaloniaFact]
    public void The_Help_page_renders_the_embedded_readme_and_switches_topic()
    {
        var upload = new UploadPageViewModel(new FakeUploaderRuntime(new AppConfig(), new FakeRunEngine()), a => a());
        var vm = new MainWindowViewModel(upload, null, UiTheme.Dark, _ => null);
        var window = new MainWindow { DataContext = vm };
        window.Show();

        vm.ShowHelpCommand.Execute().Subscribe();

        var page = window.GetVisualDescendants().OfType<Border>().First(b => b.Name == "HelpPage");
        Assert.True(page.IsVisible);
        var helpView = window.GetVisualDescendants().OfType<HelpView>().Single();
        var viewer = helpView.FindControl<MarkdownScrollViewer>("Viewer")!;
        Assert.Contains("MIRES SFTP Uploader", viewer.Markdown);

        var help = Assert.IsType<HelpViewModel>(helpView.DataContext);
        help.Selected = help.Topics[1];
        Assert.Contains("Scheduling Headless Runs", viewer.Markdown);
    }
}

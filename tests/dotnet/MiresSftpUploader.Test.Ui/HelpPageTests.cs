using System;
using System.Linq;
using Avalonia.Controls;
using Avalonia.Media;
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

    [AvaloniaTheory]
    [InlineData(UiTheme.Dark)]
    [InlineData(UiTheme.Light)]
    public void Code_in_the_Help_is_readable_in_each_theme(UiTheme theme)
    {
        var upload = new UploadPageViewModel(new FakeUploaderRuntime(new AppConfig(), new FakeRunEngine()), a => a());
        var vm = new MainWindowViewModel(upload, null, theme, _ => null);
        var window = new MainWindow { DataContext = vm };
        window.Show();
        vm.ShowHelpCommand.Execute().Subscribe();
        Avalonia.Threading.Dispatcher.UIThread.RunJobs();
        window.UpdateLayout();

        var code = window.GetVisualDescendants().Where(v => v.GetType().Name == "CTextBlock")
            .SelectMany(v => ((System.Collections.IEnumerable)v.GetType().GetProperty("Content")!.GetValue(v)!).Cast<object>())
            .Where(i => i.GetType().Name == "CCode").ToList();

        Assert.NotEmpty(code);
        foreach (var span in code)
        {
            var fg = (ISolidColorBrush)span.GetType().GetProperty("Foreground")!.GetValue(span)!;
            var bg = (ISolidColorBrush)span.GetType().GetProperty("Background")!.GetValue(span)!;
            Assert.True(Contrast(fg.Color, bg.Color) >= 4.5, $"contrast {Contrast(fg.Color, bg.Color):0.0} in {theme}");
        }
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

using System;
using Avalonia.Controls;
using MiresSftpUploader.ViewModels;

namespace MiresSftpUploader.Views;

/// <summary>The Help page. Owns its view-model so the window's view-model stays unchanged.</summary>
public partial class HelpView : UserControl
{
    public HelpView()
    {
        InitializeComponent();
        var help = HelpViewModel.Create(OpenInBrowser);
        DataContext = help;
        Viewer.Plugins.HyperlinkCommand = help.OpenLinkCommand;
    }

    private void OpenInBrowser(Uri uri)
    {
        if (TopLevel.GetTopLevel(this)?.Launcher is { } launcher) _ = launcher.LaunchUriAsync(uri);
    }
}

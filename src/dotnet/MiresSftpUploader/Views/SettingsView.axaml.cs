using System.Linq;
using System.Threading.Tasks;
using Avalonia.Controls;
using Avalonia.Input.Platform;
using Avalonia.Platform.Storage;
using MiresSftpUploader.ViewModels;

namespace MiresSftpUploader.Views;

/// <summary>The Settings page. Gives the view-model the three things only a window can do: pick a folder, copy to the clipboard, ask for confirmation.</summary>
public partial class SettingsView : UserControl
{
    public SettingsView()
    {
        InitializeComponent();
        DataContextChanged += (_, _) =>
        {
            if (DataContext is not SettingsPageViewModel vm) return;
            vm.PickFolder = PickFolderAsync;
            vm.CopyToClipboard = CopyAsync;
            vm.Confirm = (title, message) => ConfirmAsync(title, message);
            vm.ConfirmHostKey = (title, message) => ConfirmAsync(title, message, "Trust and use it");
        };
    }

    private async Task<string?> PickFolderAsync()
    {
        if (TopLevel.GetTopLevel(this) is not { } top) return null;
        var folders = await top.StorageProvider.OpenFolderPickerAsync(new FolderPickerOpenOptions { AllowMultiple = false });
        return folders.FirstOrDefault()?.TryGetLocalPath();
    }

    private async Task CopyAsync(string text)
    {
        if (TopLevel.GetTopLevel(this)?.Clipboard is { } clipboard) await clipboard.SetTextAsync(text);
    }

    private async Task<bool> ConfirmAsync(string title, string message, string? acceptLabel = null)
    {
        if (TopLevel.GetTopLevel(this) is not Window owner) return false;
        return await new ConfirmDialog(title, message, acceptLabel).ShowDialog<bool>(owner);
    }
}

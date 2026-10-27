using Terminal.Gui.ViewBase;
using Terminal.Gui.Views;

namespace MiresSftpUploader.SettingsTui.Pages;

/// <summary>Stands in for a page whose ticket has not landed yet.</summary>
public static class PlaceholderPage
{
    public static PageDefinition Definition(string title) =>
        new(title, vm => PageCatalog.GroupBadge(vm, title), _ => new FormPane([FormRows.Note("This page is not available in the Settings TUI yet.")]));
}

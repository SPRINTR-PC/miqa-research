using System.Linq;
using Terminal.Gui.ViewBase;

namespace MiresSftpUploader.SettingsTui.Pages;

/// <summary>The Appearance page: every setting of the "Appearance" group as a field row.</summary>
public static class AppearancePage
{
    public const string Title = "Appearance";
    public const string ThemeNote = "Applies to the window; the terminal UI uses its own colours.";

    public static void Register(PageCatalog catalog) =>
        catalog.Register(new PageDefinition(
            Title,
            vm => PageCatalog.GroupBadge(vm, Title),
            ctx => new FormPane(FormRows.ForGroup(ctx.Vm, Title).Append<View>(FormRows.Note(ThemeNote)))));
}

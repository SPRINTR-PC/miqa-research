using System.Linq;

namespace MiresSftpUploader.SettingsTui.Pages;

/// <summary>The Destination page: every setting of the "Destination" group as a field row. A page that is only a group of fields looks like this.</summary>
public static class DestinationPage
{
    public const string Title = "Destination";

    public static void Register(PageCatalog catalog) =>
        catalog.Register(new PageDefinition(
            Title,
            vm => PageCatalog.GroupBadge(vm, Title),
            ctx => new FormPane(FormRows.ForGroup(ctx.Vm, Title))));
}

namespace MiresSftpUploader.SettingsTui.Pages;

/// <summary>The Archives page: every setting of the "Archives" group as a field row.</summary>
public static class ArchivesPage
{
    public const string Title = "Archives";

    public static void Register(PageCatalog catalog) =>
        catalog.Register(new PageDefinition(
            Title,
            vm => PageCatalog.GroupBadge(vm, Title),
            ctx => new FormPane(FormRows.ForGroup(ctx.Vm, Title))));
}

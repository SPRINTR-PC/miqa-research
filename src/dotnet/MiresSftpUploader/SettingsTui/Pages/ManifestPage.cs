namespace MiresSftpUploader.SettingsTui.Pages;

/// <summary>The Manifest page: every setting of the "Manifest" group as a field row.</summary>
public static class ManifestPage
{
    public const string Title = "Manifest";

    public static void Register(PageCatalog catalog) =>
        catalog.Register(new PageDefinition(
            Title,
            vm => PageCatalog.GroupBadge(vm, Title),
            ctx => new FormPane(FormRows.ForGroup(ctx.Vm, Title))));
}

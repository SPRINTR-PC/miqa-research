namespace MiresSftpUploader.SettingsTui.Pages;

/// <summary>The Appearance page: every setting of the "Appearance" group as a field row.</summary>
public static class AppearancePage
{
    public const string Title = "Appearance";

    public static void Register(PageCatalog catalog) =>
        catalog.Register(new PageDefinition(
            Title,
            vm => PageCatalog.GroupBadge(vm, Title),
            ctx => new FormPane(FormRows.ForGroup(ctx.Vm, Title))));
}

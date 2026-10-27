namespace MiresSftpUploader.SettingsTui.Pages;

/// <summary>The Ignore Rules page: every setting of the "Ignore Rules" group as a field row.</summary>
public static class IgnoreRulesPage
{
    public const string Title = "Ignore Rules";

    public static void Register(PageCatalog catalog) =>
        catalog.Register(new PageDefinition(
            Title,
            vm => PageCatalog.GroupBadge(vm, Title),
            ctx => new FormPane(FormRows.ForGroup(ctx.Vm, Title))));
}

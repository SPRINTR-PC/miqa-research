namespace MiresSftpUploader.SettingsTui.Pages;

/// <summary>The Reports and logs page: every setting of the "Reports and logs" group as a field row.</summary>
public static class ReportsAndLogsPage
{
    public const string Title = "Reports and logs";

    public static void Register(PageCatalog catalog) =>
        catalog.Register(new PageDefinition(
            Title,
            vm => PageCatalog.GroupBadge(vm, Title),
            ctx => new FormPane(FormRows.ForGroup(ctx.Vm, Title))));
}

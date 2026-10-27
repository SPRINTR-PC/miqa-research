namespace MiresSftpUploader.SettingsTui.Pages;

/// <summary>The Upload page: every setting of the "Upload" group as a field row.</summary>
public static class UploadPage
{
    public const string Title = "Upload";

    public static void Register(PageCatalog catalog) =>
        catalog.Register(new PageDefinition(
            Title,
            vm => PageCatalog.GroupBadge(vm, Title),
            ctx => new FormPane(FormRows.ForGroup(ctx.Vm, Title))));
}

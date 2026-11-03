using System.Collections.Generic;
using System.Linq;
using Terminal.Gui.ViewBase;

namespace MiresSftpUploader.SettingsTui.Pages;

/// <summary>The Destination page: every setting of the "Destination" group as a field row. A page that is only a group of fields looks like this.</summary>
public static class DestinationPage
{
    public const string Title = "Destination";

    public static void Register(PageCatalog catalog) =>
        catalog.Register(new PageDefinition(
            Title,
            vm => PageCatalog.GroupBadge(vm, Title),
            ctx => new FormPane(FormRows.ForGroup(ctx.Vm, Title).Concat(CheckButton(ctx)))));

    // Checks the connection as edited. Without a Host Key Fingerprint it offers to take the one the server presents (also F5).
    private static IEnumerable<View> CheckButton(PageContext ctx)
    {
        if (ctx.CheckConnection is not { } check) yield break;
        yield return FormRows.Btn("Check _connection (F5)", check);
        yield return FormRows.Note("Works without a Host Key Fingerprint: you are shown the server's and asked whether to use it.");
    }
}

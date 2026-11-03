using System;
using System.Collections.Generic;
using System.Linq;
using MiresSftpUploader.SettingsTui.Pages;
using MiresSftpUploader.ViewModels;
using Terminal.Gui.App;
using Terminal.Gui.ViewBase;

namespace MiresSftpUploader.SettingsTui;

/// <summary>
/// What a page needs to build its content. <paramref name="RefreshChrome"/> redraws the window's badges and status line; a page calls it when
/// something the chrome shows changes without a field changing (a rule added, a rule's pattern edited).
/// </summary>
public sealed record PageContext(IApplication App, SettingsPageViewModel Vm, ITuiDialogs Dialogs, Action? RefreshChrome = null, Action? CheckConnection = null);

/// <summary>
/// One page of the sidebar. <paramref name="Badge"/> returns "" , "●" (changed), "!" (error) or "L" (locked) and is evaluated on every
/// refresh; <paramref name="Build"/> returns the page's content view, called each time the page is shown or the view models are reloaded.
/// </summary>
public sealed record PageDefinition(string Title, Func<SettingsPageViewModel, string> Badge, Func<PageContext, View> Build);

/// <summary>
/// The sidebar's pages, in fixed order. Every page starts as a placeholder; a page's own file replaces its entry with
/// <see cref="Register"/> (one line in <see cref="CreateDefault"/> per page).
/// </summary>
public sealed class PageCatalog
{
    /// <summary>The 11 pages, in sidebar order. Titles equal the group names of <see cref="SettingFieldViewModel.Group"/> where there is one.</summary>
    public static IReadOnlyList<string> Titles { get; } =
    [
        "Destination", "Secrets", "Sources", "Upload", "Ignore Rules", "Archives",
        "Archive Rules", "Manifest", "Data Directory", "Reports and logs", "Appearance",
    ];

    private readonly Dictionary<string, PageDefinition> _pages = [];

    public PageCatalog()
    {
        foreach (var title in Titles) _pages[title] = PlaceholderPage.Definition(title);
    }

    public IReadOnlyList<PageDefinition> Pages => Titles.Select(t => _pages[t]).ToList();

    /// <summary>Replaces the placeholder (or an earlier registration) of <paramref name="page"/>'s title.</summary>
    public PageCatalog Register(PageDefinition page)
    {
        if (!_pages.ContainsKey(page.Title)) throw new ArgumentException($"'{page.Title}' is not one of the Settings TUI pages.", nameof(page));
        _pages[page.Title] = page;
        return this;
    }

    /// <summary>The catalogue the Settings TUI ships with. Each page ticket adds its <c>Register</c> line here.</summary>
    public static PageCatalog CreateDefault()
    {
        var catalog = new PageCatalog();
        DestinationPage.Register(catalog);
        DataDirectoryPage.Register(catalog);
        ArchiveRulesPage.Register(catalog);
        UploadPage.Register(catalog);
        IgnoreRulesPage.Register(catalog);
        ArchivesPage.Register(catalog);
        ManifestPage.Register(catalog);
        ReportsAndLogsPage.Register(catalog);
        AppearancePage.Register(catalog);
        SourcesPage.Register(catalog);
        SecretsPage.Register(catalog);
        return catalog;
    }

    /// <summary>The badge for a page that is just a group of fields: "!" beats "●" beats "L".</summary>
    public static string GroupBadge(SettingsPageViewModel vm, string group)
    {
        var fields = vm.Fields.Where(f => f.Group == group).ToList();
        return fields.Any(f => f.HasError) ? "!" : fields.Any(f => f.IsChanged) ? "●" : fields.Any(f => f.IsLocked) ? "L" : "";
    }
}

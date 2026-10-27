using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Linq;
using MiresSftpUploader.ViewModels;
using Terminal.Gui.Drawing;
using Terminal.Gui.ViewBase;
using Terminal.Gui.Views;

namespace MiresSftpUploader.SettingsTui;

/// <summary>The list of pages on the left. Each row is a badge column (<c>●</c> changed, <c>!</c> error, <c>L</c> locked) and the page title.</summary>
public sealed class PageSidebar : ListView
{
    public const int OuterWidth = 20;

    private readonly ObservableCollection<string> _items;
    private readonly IReadOnlyList<PageDefinition> _pages;

    public PageSidebar(IReadOnlyList<PageDefinition> pages, SettingsPageViewModel vm)
    {
        _pages = pages;
        _items = new ObservableCollection<string>(Labels(vm));
        X = 0;
        Y = 1;
        Width = OuterWidth;
        Height = Dim.Fill(2);
        Source = new ListWrapper<string>(_items);
        BorderStyle = LineStyle.Single;
        Title = "Settings";
        this.Apply(Theme.Nav);
        SelectedItem = 0;
    }

    /// <summary>The sidebar rows as text, e.g. <c>● Destination</c>.</summary>
    public IReadOnlyList<string> Items => _items;

    /// <summary>Updates the badges in place; assigning a new Source would make the sidebar take the focus from the form being edited.</summary>
    public void RefreshBadges(SettingsPageViewModel vm) => ListSync.Update(_items, Labels(vm));

    private List<string> Labels(SettingsPageViewModel vm) =>
        _pages.Select(p => (p.Badge(vm) is { Length: > 0 } b ? b : " ") + " " + p.Title).ToList();
}

using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Linq;
using Terminal.Gui.Input;
using Terminal.Gui.ViewBase;
using Terminal.Gui.Views;

namespace MiresSftpUploader.SettingsTui;

/// <summary>
/// A list with Add and Remove on the left and the selected item's form on the right. Enter or Right in the list enters the form, Esc goes back
/// (see <see cref="FocusLevels"/>), Tab walks list, Add, Remove and the form's inputs. The list is updated in place so that typing in a name
/// keeps the focus. The owner reports changes: <see cref="Reload"/> after an item's text changed, <see cref="ItemsChanged"/> after items were added or removed.
/// </summary>
public sealed class MasterDetail : View
{
    public const int ListWidth = 30;

    private readonly Func<IReadOnlyList<string>> _names;
    private readonly Action _add;
    private readonly Action<int> _remove;
    private readonly Func<int, View> _detail;
    private readonly ObservableCollection<string> _items;
    private readonly ListView _list;
    private readonly View _detailHost;
    private bool _syncing;
    private int _shown = -2;

    /// <param name="names">One list row per item.</param>
    /// <param name="add">Adds an item at the end.</param>
    /// <param name="remove">Removes the item at the index.</param>
    /// <param name="detail">Builds the form of the item at the index.</param>
    /// <param name="editable">False disables Add and Remove.</param>
    /// <param name="banner">Shown above the list (a locked list's reason), or null.</param>
    public MasterDetail(Func<IReadOnlyList<string>> names, Action add, Action<int> remove, Func<int, View> detail, bool editable, string? banner = null)
    {
        _names = names;
        _add = add;
        _remove = remove;
        _detail = detail;
        Width = Dim.Fill();
        Height = Dim.Fill();
        CanFocus = true;
        TabStop = TabBehavior.NoStop;
        _items = new ObservableCollection<string>(names());
        var top = banner is null ? 0 : 1;
        if (banner is not null) Add(new Label { Width = Dim.Fill(), Text = "🔒 " + banner }.Apply(Theme.Locked));
        _list = new ListView { X = 0, Y = top, Width = ListWidth, Height = Dim.Fill(2), Source = new ListWrapper<string>(_items) };
        var addButton = FormRows.Btn("Add", AddClicked);
        addButton.Y = Pos.AnchorEnd(1);
        addButton.Enabled = editable;
        var removeButton = FormRows.Btn("Remove", RemoveClicked);
        removeButton.Y = Pos.AnchorEnd(1);
        removeButton.X = 9;
        removeButton.Enabled = editable;
        _detailHost = new View { X = ListWidth + 2, Y = top, Width = Dim.Fill(), Height = Dim.Fill(), CanFocus = true, TabStop = TabBehavior.NoStop };
        Add(_list, addButton, removeButton, _detailHost);
        FocusLevels.Link(_list, _detailHost);
        _list.ValueChanged += (_, _) => { if (!_syncing) ShowSelected(); };
        KeyDown += OnKey;
        if (_items.Count > 0) _list.SelectedItem = 0;
        ShowSelected();
    }

    public ListView List => _list;

    public int SelectedIndex => _list.SelectedItem is { } i && i >= 0 && i < _items.Count ? i : -1;

    /// <summary>The list rows as text.</summary>
    public IReadOnlyList<string> Rows => _items;

    /// <summary>Refreshes the list rows after an item's text changed; the form stays as it is.</summary>
    public void Reload() => Sync(null);

    /// <summary>Refreshes the list and rebuilds the form after items were added or removed. <paramref name="select"/> picks the selected index.</summary>
    public void ItemsChanged(int? select = null)
    {
        Sync(select);
        _shown = -2;
        ShowSelected();
    }

    private void Sync(int? select)
    {
        var keep = select ?? SelectedIndex;
        var names = _names();
        _syncing = true;
        try
        {
            ListSync.Update(_items, names);
            if (_items.Count > 0) _list.SelectedItem = Math.Clamp(keep, 0, _items.Count - 1);
        }
        finally
        {
            _syncing = false;
        }
    }

    private void ShowSelected()
    {
        var index = SelectedIndex;
        if (index == _shown) return;
        _shown = index;
        foreach (var old in _detailHost.SubViews.ToList()) { _detailHost.Remove(old); old.Dispose(); }
        if (index >= 0) _detailHost.Add(_detail(index));
    }

    private void AddClicked()
    {
        var before = _names().Count;
        _add();
        var count = _names().Count;
        ItemsChanged(Math.Max(0, count - 1));
        if (count > before) FocusLevels.FocusFirstInput(_detailHost);
    }

    private void RemoveClicked()
    {
        if (SelectedIndex is >= 0 and var i) _remove(i);
        ItemsChanged();
    }

    private void OnKey(object? sender, Key k)
    {
        var dir = k == Key.Tab ? 1 : k == Key.Tab.WithShift ? -1 : 0;
        if (dir == 0) return;
        var inputs = FocusLevels.Inputs(this);
        var at = inputs.IndexOf(MostFocused!);
        var next = at + dir;
        if (at < 0 || next < 0 || next >= inputs.Count) return;
        inputs[next].SetFocus();
        k.Handled = true;
    }
}

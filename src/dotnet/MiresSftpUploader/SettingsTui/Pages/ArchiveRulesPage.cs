using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Linq;
using System.Reactive.Linq;
using MiresSftpUploader.ViewModels;
using Terminal.Gui.Input;
using Terminal.Gui.ViewBase;
using Terminal.Gui.Views;

namespace MiresSftpUploader.SettingsTui.Pages;

/// <summary>
/// The Archive Rules page: the global rules as a list (in added order, no reorder) with Add and Remove, and the selected rule's form beside it.
/// Add selects the new rule with the cursor in its name. The rule list is updated in place so typing a name keeps the focus.
/// </summary>
public static class ArchiveRulesPage
{
    public const string Title = "Archive Rules";

    private const string NoRules = "(no rules: every file is uploaded on its own)";
    private const string NewRule = "(new rule)";

    public static void Register(PageCatalog catalog) =>
        catalog.Register(new PageDefinition(
            Title,
            vm => vm.ArchiveRules.HasError ? "!" : vm.ArchiveRules.IsChanged ? "●" : vm.ArchiveRules.IsLocked ? "L" : "",
            ctx => new RulesPane(ctx.Vm.ArchiveRules, ctx.RefreshChrome)));

    private sealed class RulesPane : View
    {
        private readonly ArchiveRulesViewModel _rules;
        private readonly Action? _refreshChrome;
        private readonly ObservableCollection<string> _names;
        private readonly ListView _list;
        private readonly FormPane _detail;
        private readonly Label _error = new() { Width = Dim.Fill() };

        public RulesPane(ArchiveRulesViewModel rules, Action? refreshChrome)
        {
            _rules = rules;
            _refreshChrome = refreshChrome;
            Width = Dim.Fill();
            Height = Dim.Fill();
            CanFocus = true;
            TabStop = TabBehavior.NoStop;

            var banner = rules.IsLocked
                ? FormRows.Note("🔒 Locked: from an environment variable or a Machine Config you cannot write.").Apply(Theme.Locked)
                : FormRows.Note("First matching rule wins; a group with fewer than Min files stays loose.");
            _names = new ObservableCollection<string>(Names());
            _list = new ListView { X = 0, Y = 2, Width = 26, Height = Dim.Fill(2), Source = new ListWrapper<string>(_names) };
            _detail = new FormPane([]) { X = 28, Y = 2, Width = Dim.Fill(), Height = Dim.Fill() };
            var add = FormRows.Btn("Add", Add);
            add.Y = Pos.AnchorEnd(1);
            add.Enabled = rules.IsEditable;
            var remove = FormRows.Btn("Remove", Remove);
            remove.Y = Pos.AnchorEnd(1);
            remove.X = 8;
            remove.Enabled = rules.IsEditable;
            Add(banner, _list, add, remove, _detail);
            FocusLevels.Link(_list, _detail);

            _list.ValueChanged += (_, _) => ShowSelected();
            rules.Rules.CollectionChanged += OnRulesChanged;
            rules.PropertyChanged += OnRulesProperty;
            if (rules.Rules.Count > 0) _list.SelectedItem = 0;
            ShowSelected();
        }

        private IReadOnlyList<string> Names() =>
            _rules.Rules.Count == 0 ? [NoRules] : _rules.Rules.Select(r => r.Name.Length == 0 ? NewRule : r.Name).ToList();

        private ArchiveRuleEditorViewModel? Selected =>
            _list.SelectedItem is { } i && i >= 0 && i < _rules.Rules.Count ? _rules.Rules[i] : null;

        private void Add()
        {
            _rules.AddRuleCommand.Fire(this);
            if (_rules.Rules.Count == 0) return;
            _list.SelectedItem = _rules.Rules.Count - 1;
            ShowSelected();
            _detail.FocusFirstInput();
        }

        private void Remove()
        {
            if (Selected is { } rule) _rules.RemoveRuleCommand.Fire(rule, this);
        }

        private void OnRulesChanged(object? sender, EventArgs e)
        {
            ListSync.Update(_names, Names());
            _list.SelectedItem = Math.Clamp(_list.SelectedItem ?? 0, 0, Math.Max(0, _rules.Rules.Count - 1));
            ShowSelected();
        }

        private void OnRulesProperty(object? sender, PropertyChangedEventArgs e)
        {
            ListSync.Update(_names, Names());
            _error.Text = _rules.HasError ? "✗ " + _rules.Error : "";
            _error.SetScheme(Theme.Error);
            _refreshChrome?.Invoke();
        }

        private ArchiveRuleEditorViewModel? _shown;

        private void ShowSelected()
        {
            var rule = Selected;
            if (ReferenceEquals(rule, _shown)) return;
            _shown = rule;
            if (rule is null) { _detail.ReplaceRows([]); return; }
            var e = _rules.IsEditable;
            _error.Text = _rules.HasError ? "✗ " + _rules.Error : "";
            _error.SetScheme(Theme.Error);
            _detail.ReplaceRows([
                FormRows.TextRow("Rule name", () => rule.Name, v => rule.Name = v, e),
                FormRows.TextRow("Pattern (regex)", () => rule.Pattern, v => rule.Pattern = v, e),
                FormRows.ChoiceRow("One Archive per", ArchiveRuleEditorViewModel.GroupingNames, () => rule.Grouping, v => rule.Grouping = v, e),
                FormRows.TextRow("Archive name", () => rule.ArchiveName, v => rule.ArchiveName = v, e),
                FormRows.TextRow("Min files", () => rule.MinFiles, v => rule.MinFiles = v, e),
                FormRows.Note("{rule}, {dir} and {date} are replaced in the Archive name."),
                _error,
            ]);
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing)
            {
                _rules.Rules.CollectionChanged -= OnRulesChanged;
                _rules.PropertyChanged -= OnRulesProperty;
            }

            base.Dispose(disposing);
        }
    }
}

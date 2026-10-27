using System;
using System.Linq;
using MiresSftpUploader.ViewModels;
using Terminal.Gui.App;
using Terminal.Gui.ViewBase;
using Terminal.Gui.Views;

namespace MiresSftpUploader.SettingsTui.Pages;

/// <summary>
/// The content of the per-Source Archive Rules dialog: a list of rules with Add/Remove and the selected rule's form, over an
/// <see cref="ArchiveRulesViewModel"/>. Self-contained and small; the global Archive Rules page does not depend on it.
/// </summary>
public static class SourceArchiveRulesEditor
{
    /// <param name="onError">Shows a failed Add or Remove; the dialog sits above the window, so it cannot be found through the view tree.</param>
    public static View Build(IApplication app, ArchiveRulesViewModel rules, Action<Exception> onError)
    {
        MasterDetail master = null!;
        master = new MasterDetail(
            () => rules.Rules.Select(r => r.Name.Length == 0 ? "(new rule)" : r.Name).ToList(),
            () => rules.AddRuleCommand.Fire(onError),
            i => rules.RemoveRuleCommand.Fire(rules.Rules[i], onError),
            i => Form(rules, rules.Rules[i], () => master.Reload()),
            rules.IsEditable,
            rules.IsLocked ? "Locked: set by an environment variable or a Machine Config you cannot write." : null);
        return master;
    }

    private static FormPane Form(ArchiveRulesViewModel rules, ArchiveRuleEditorViewModel r, Action namesChanged)
    {
        var e = rules.IsEditable;
        var problem = new Label { Width = Dim.Fill(1), Height = 1, Text = rules.HasError ? "✗ " + rules.Error : "" };
        problem.SetScheme(Theme.Error);
        return new FormPane([
            FormRows.TextRow("Rule name", () => r.Name, v => { r.Name = v; namesChanged(); }, e),
            FormRows.TextRow("Pattern (regex)", () => r.Pattern, v => r.Pattern = v, e),
            FormRows.ChoiceRow("One Archive per", ArchiveRuleEditorViewModel.GroupingNames, () => r.Grouping, v => r.Grouping = v, e),
            FormRows.TextRow("Archive name", () => r.ArchiveName, v => r.ArchiveName = v, e),
            FormRows.TextRow("Min files", () => r.MinFiles, v => r.MinFiles = v, e),
            FormRows.Note("First matching rule wins. {rule}, {dir} and {date} are replaced in the Archive name."),
            problem,
        ]);
    }
}

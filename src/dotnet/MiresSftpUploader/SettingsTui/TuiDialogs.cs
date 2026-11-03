using System.Collections.Generic;
using System.Collections.ObjectModel;
using MiresSftpUploader.SettingsTui.Pages;
using MiresSftpUploader.ViewModels;
using Terminal.Gui.App;
using Terminal.Gui.ViewBase;
using Terminal.Gui.Views;

namespace MiresSftpUploader.SettingsTui;

public enum UnsavedChoice { Save, Discard, Cancel }

/// <summary>
/// Every modal question the Settings TUI asks. A nested modal <c>Run</c> blocks a headless snapshot, so tests replace this seam
/// with a fake that records the question and returns a scripted answer.
/// </summary>
public interface ITuiDialogs
{
    /// <summary>Two buttons (the first is <paramref name="acceptLabel"/>), Cancel is the default, Esc cancels. True when the user confirmed.</summary>
    bool Confirm(string title, string message, string acceptLabel = "_Change");

    /// <summary>Quit with unsaved changes. <paramref name="canSave"/> is false while errors exist (Save is then absent).</summary>
    UnsavedChoice AskUnsaved(bool canSave);

    /// <summary>The F4 list of every problem and warning.</summary>
    void ShowIssues(IReadOnlyList<string> lines);

    void ShowMessage(string title, string message);

    /// <summary>Quit while a Run is active: "Cancel the Run and quit" or "Back". True when the user chose to cancel and quit; Back is the default.</summary>
    bool AskCancelRunAndQuit();

    /// <summary>A Source's own Archive Rules, edited in a dialog until the user closes it.</summary>
    void EditArchiveRules(string title, ArchiveRulesViewModel rules);
}

/// <summary>The real dialogs, run modally on the application.</summary>
public sealed class TerminalGuiDialogs(IApplication app) : ITuiDialogs
{
    // Terminal.Gui makes the last button the default, so Cancel goes last; Esc returns null, which is not a confirmation.
    public bool Confirm(string title, string message, string acceptLabel = "_Change") => MessageBox.Query(app, title, message, acceptLabel, "_Cancel") == 0;

    public UnsavedChoice AskUnsaved(bool canSave)
    {
        if (!canSave)
            return MessageBox.Query(app, "Unsaved changes", "There are unsaved changes with problems, so they cannot be saved.", "_Discard", "_Keep editing") == 0
                ? UnsavedChoice.Discard
                : UnsavedChoice.Cancel;
        return MessageBox.Query(app, "Unsaved changes", "Save the changes before quitting?", "_Save", "_Discard", "_Cancel") switch
        {
            0 => UnsavedChoice.Save,
            1 => UnsavedChoice.Discard,
            _ => UnsavedChoice.Cancel,
        };
    }

    public void ShowIssues(IReadOnlyList<string> lines)
    {
        var dialog = new Dialog { Title = "Issues", Width = Dim.Percent(90), Height = Dim.Percent(60) };
        dialog.Add(new ListView { Width = Dim.Fill(), Height = Dim.Fill(2), Source = new ListWrapper<string>(new ObservableCollection<string>(lines)) });
        dialog.AddButton(new Button { Title = "_Close" });
        app.Run(dialog);
        dialog.Dispose();
    }

    public void ShowMessage(string title, string message) => MessageBox.Query(app, title, message, "_OK");

    public bool AskCancelRunAndQuit() =>
        MessageBox.Query(app, "A Run is active", "Cancel the Run and quit, or go back to it?", "_Cancel the Run and quit", "_Back") == 0;

    public void EditArchiveRules(string title, ArchiveRulesViewModel rules)
    {
        var dialog = new Dialog { Title = title, Width = Dim.Percent(90), Height = Dim.Percent(80) };
        dialog.Add(SourceArchiveRulesEditor.Build(app, rules, e => ShowMessage("Error", e.Message)));
        dialog.AddButton(new Button { Title = "_Close" });
        app.Run(dialog);
        dialog.Dispose();
    }
}

#pragma warning disable CS0618 // TextView: the multi-line box for Lines settings; its replacement is a separate package
using MiresSftpUploader.Core;
using MiresSftpUploader.SettingsTui;
using MiresSftpUploader.ViewModels;
using Terminal.Gui.App;
using Terminal.Gui.Drivers;
using Terminal.Gui.Input;
using Terminal.Gui.Testing;
using Terminal.Gui.ViewBase;

namespace MiresSftpUploader.Test.Unit;

/// <summary>Answers the Settings TUI's dialogs without opening one (a nested modal Run blocks a headless snapshot) and records what was asked.</summary>
public sealed class FakeTuiDialogs : ITuiDialogs
{
    public List<(string Title, string Message)> Confirmations { get; } = [];
    public Queue<bool> ConfirmAnswers { get; } = new();
    public List<bool> UnsavedAsked { get; } = [];
    public Queue<UnsavedChoice> UnsavedAnswers { get; } = new();
    public List<IReadOnlyList<string>> IssueLists { get; } = [];
    public List<(string Title, string Message)> Messages { get; } = [];

    public bool Confirm(string title, string message, string acceptLabel = "_Change")
    {
        Confirmations.Add((title, message));
        return ConfirmAnswers.Count > 0 && ConfirmAnswers.Dequeue();
    }

    public UnsavedChoice AskUnsaved(bool canSave)
    {
        UnsavedAsked.Add(canSave);
        return UnsavedAnswers.Count > 0 ? UnsavedAnswers.Dequeue() : UnsavedChoice.Cancel;
    }

    public void ShowIssues(IReadOnlyList<string> lines) => IssueLists.Add(lines);

    public int RunQuitAsked { get; private set; }

    /// <summary>Runs while the Run-quit question is open, as a signal would in the real modal.</summary>
    public Action? OnAskCancelRunAndQuit { get; set; }
    public Queue<bool> RunQuitAnswers { get; } = new();

    public bool AskCancelRunAndQuit()
    {
        RunQuitAsked++;
        OnAskCancelRunAndQuit?.Invoke();
        return RunQuitAnswers.Count > 0 && RunQuitAnswers.Dequeue();
    }

    public void ShowMessage(string title, string message) => Messages.Add((title, message));

    public List<(string Title, ArchiveRulesViewModel Rules)> ArchiveRuleDialogs { get; } = [];

    public void EditArchiveRules(string title, ArchiveRulesViewModel rules) => ArchiveRuleDialogs.Add((title, rules));
}

/// <summary>
/// A Settings TUI running on Terminal.Gui's headless ANSI driver: one <c>Application.Create()</c> per harness, so tests run in parallel.
/// Keys are injected the way a user types them; the screen is read back from the driver's buffer.
/// </summary>
public sealed class SettingsTuiHarness : IDisposable
{
    public IApplication App { get; }
    public SettingsTuiWindow Window { get; }
    public SettingsPageViewModel Page { get; }
    public FakeTuiDialogs Dialogs { get; }

    public SettingsTuiHarness(Configuration configuration, int width = 100, int height = 32, FakeTuiDialogs? dialogs = null, SettingsPageViewModel? page = null)
    {
        Dialogs = dialogs ?? new FakeTuiDialogs();
        Page = page ?? new SettingsPageViewModel(configuration, WritableDataDirectory.Check, _ => long.MaxValue);
        App = Application.Create();
        App.Init(DriverRegistry.Names.ANSI);
        App.Driver!.SetScreenSize(width, height);
        Window = new SettingsTuiWindow(App, Page, Dialogs);
        App.Begin(Window);
        Draw();
    }

    public void Draw() => App.LayoutAndDraw(true);

    public void Resize(int width, int height)
    {
        App.Driver!.SetScreenSize(width, height);
        Draw();
    }

    public void Press(Key key)
    {
        App.InjectKey(key);
        Draw();
    }

    public void Press(params Key[] keys)
    {
        foreach (var key in keys) Press(key);
    }

    public void Type(string text)
    {
        foreach (var c in text) Press((Key)c);
    }

    public string Screen
    {
        get
        {
            Draw();
            return App.Driver!.ToString() ?? "";
        }
    }

    /// <summary>One string per screen row (the driver's trailing line break is dropped).</summary>
    public string[] Lines => Screen.TrimEnd('\n').Split('\n');

    /// <summary>The first screen row containing <paramref name="text"/>, or null.</summary>
    public string? Row(string text) => Lines.FirstOrDefault(l => l.Contains(text, StringComparison.Ordinal));

    /// <summary>The sidebar row of a page as drawn (badge column and title), e.g. <c>● Destination</c>.</summary>
    public string SidebarRow(string title) =>
        Lines.First(l => l.StartsWith('│') && l.Contains(title, StringComparison.Ordinal)).Split('│')[1].TrimEnd();

    public bool Shows(string text) => Row(text) is not null;

    public View? Focused => App.Navigation?.GetFocused();

    /// <summary>The focused control and its ancestors, e.g. <c>TextField &lt; FieldRow &lt; FormPane</c>.</summary>
    public string FocusPath
    {
        get
        {
            var path = new List<string>();
            for (var v = Focused; v is not null; v = v.SuperView) path.Add(v.GetType().Name);
            return string.Join(" < ", path);
        }
    }

    /// <summary>The label of the Setting whose row has the focus, or null when focus is elsewhere (sidebar, buttons).</summary>
    public string? FocusedFieldLabel
    {
        get
        {
            for (var v = Focused; v is not null; v = v.SuperView)
                if (v is FieldRow row) return row.Field.Label;
            return null;
        }
    }

    /// <summary>The form row of the Setting labelled <paramref name="label"/> on the current page.</summary>
    public FieldRow FieldRowFor(string label)
    {
        static IEnumerable<View> All(View v) => v.SubViews.SelectMany(c => new[] { c }.Concat(All(c)));
        return All(Window).OfType<FieldRow>().First(r => r.Field.Label == label);
    }

    public bool SidebarFocused => Focused is PageSidebar;

    /// <summary>Presses Tab until the Setting labelled <paramref name="label"/> has the focus (at most 40 presses).</summary>
    public void TabTo(string label)
    {
        for (var i = 0; i < 40 && FocusedFieldLabel != label; i++) Press(Key.Tab);
        Assert.AreEqual(label, FocusedFieldLabel, $"could not Tab to {label}\n{FocusPath}");
    }

    /// <summary>The text of the focused text box, or null when another control has the focus.</summary>
    public string? FocusedText => (Focused as Terminal.Gui.Views.TextField)?.Text ?? (Focused as Terminal.Gui.Views.TextView)?.Text;

    public void Dispose()
    {
        Window.Dispose();
        App.Dispose();
    }
}

/// <summary>Fixture for Settings TUI tests: a valid Machine Config in a temp folder and a harness on top of it.</summary>
public abstract class SettingsTuiTestBase : ConfigurationTestBase
{
    private readonly List<SettingsTuiHarness> _open = [];

    [TestCleanup]
    public void CloseHarnesses()
    {
        foreach (var h in _open) h.Dispose();
        _open.Clear();
    }

    protected SettingsTuiHarness Start(Configuration? configuration = null, int width = 100, int height = 32, FakeTuiDialogs? dialogs = null, SettingsPageViewModel? page = null)
    {
        var cfg = configuration ?? Create(ValidMachine().ToJsonString());
        var h = new SettingsTuiHarness(cfg, width, height, dialogs, page);
        _open.Add(h);
        return h;
    }
}

/// <summary>A Data Directory check that always finds a writable directory, so a TUI test does not depend on the machine's real one (absent on CI).</summary>
internal static class WritableDataDirectory
{
    public static MiresSftpUploader.Core.DataDirectoryAccess Check(string path) =>
        new(path, true, true, "alice", "mires-uploader", 0, long.MaxValue, false, "", null);
}

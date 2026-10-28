using System.Data;
using MiresSftpUploader.Core;
using MiresSftpUploader.SettingsTui;
using MiresSftpUploader.Test.Support;
using MiresSftpUploader.Tui;
using MiresSftpUploader.ViewModels;
using Terminal.Gui.Input;
using Terminal.Gui.Testing;
using Terminal.Gui.ViewBase;
using Terminal.Gui.Views;

namespace MiresSftpUploader.Test.Unit;

/// <summary>A stand-in Upload page with a focused <see cref="TableView"/>, which swallows letters and digits for type-to-search.</summary>
public sealed class ProbePage : View, IShellPage
{
    private readonly TableView _table = new() { X = 0, Y = 0, Width = Dim.Fill(), Height = Dim.Fill() };

    public ProbePage()
    {
        CanFocus = true;
        var data = new DataTable();
        data.Columns.Add("File");
        foreach (var name in new[] { "alpha.svs", "beta.svs", "rhubarb.svs", "delta.svs" }) data.Rows.Add(name);
        _table.Table = new DataTableSource(data);
        Add(_table);
    }

    public List<Key> Handled { get; } = [];

    public string StatusText => "probe status";

    public string KeyHints => "R Run  1-4 Filter";

    public event Action? ChromeChanged { add { } remove { } }

    public bool HandleKey(Key key)
    {
        if (key != Key.R && key != Key.D1) return false;
        Handled.Add(key);
        return true;
    }

    public void FocusDefault() => _table.SetFocus();
}

[TestClass]
[DoNotParallelize] // each test runs a TuiTestHost (own thread + Terminal.Gui loop); started alongside hundreds of other tests the loop starves and "the TUI did not start"
public sealed class TuiShellNavigationTests : ConfigurationTestBase
{
    private static readonly Key[] FunctionKeys = [Key.F9, Key.F10, Key.F11, Key.F12];
    private static readonly ShellTab[] Tabs = [ShellTab.Upload, ShellTab.History, ShellTab.Settings, ShellTab.Help];

    private readonly List<TuiTestHost> _hosts = [];

    [TestCleanup]
    public void CloseHosts()
    {
        foreach (var h in _hosts) h.Dispose();
    }

    private sealed record Started(TuiTestHost Host, TuiShell Shell, SettingsPageViewModel Page, FakeTuiDialogs Dialogs, ProbePage Probe);

    private Started Start(ShellTab tab = ShellTab.Upload, int width = 100, int height = 32)
    {
        var page = new SettingsPageViewModel(Create(ValidMachine().ToJsonString()), WritableDataDirectory.Check, _ => long.MaxValue);
        var dialogs = new FakeTuiDialogs();
        var probe = new ProbePage();
        TuiShell? shell = null;
        var host = new TuiTestHost(app => shell = new TuiShell(app, page, dialogs, tab, probe), width, height);
        _hosts.Add(host);
        host.WaitUntil(() => shell!.IsInitialized, "shell initialised");
        return new Started(host, shell!, page, dialogs, probe);
    }

    private static ShellTab CurrentOf(Started s) => s.Host.OnUi(() => s.Shell.Current);

    [TestMethod, Timeout(60000)]
    public void F9_to_F12_switch_the_page_from_every_focus()
    {
        var s = Start();
        var foci = new List<Action>
        {
            () => s.Host.Press(Key.F9),                              // probe table
            () => { s.Host.Press(Key.F11); },                        // Settings sidebar
            () => { s.Host.Press(Key.F11); s.Host.Press(Key.Enter); }, // inside the Settings form
            () => s.Host.Press(Key.F10),                             // History
            () => s.Host.Press(Key.F12),                             // Help
        };

        foreach (var focus in foci)
        foreach (var (key, expected) in FunctionKeys.Zip(Tabs))
        {
            focus();
            s.Host.Press(key);
            Assert.AreEqual(expected, CurrentOf(s), $"{key} from {s.Host.FocusPath}");
        }
    }

    [TestMethod, Timeout(60000)]
    public void F_keys_are_ignored_while_a_dialog_is_open()
    {
        var s = Start();
        var duringDialog = (ShellTab?)null;
        using var closed = new ManualResetEventSlim();
        // A modal loop only runs timeouts, and the test thread must not touch the loop meanwhile: the keys are injected by a timeout.
        s.Host.Post(() =>
        {
            s.Host.App.AddTimeout(TimeSpan.FromMilliseconds(100), () =>
            {
                s.Host.App.InjectKey(Key.F11);
                duringDialog = s.Shell.Current;
                s.Host.App.InjectKey(Key.Esc);
                return false;
            });
            MessageBox.Query(s.Host.App, "Question", "Really?", "_Yes", "_No");
            closed.Set();
        });

        Assert.IsTrue(closed.Wait(TimeSpan.FromSeconds(20)), "the dialog did not close");
        Assert.AreEqual(ShellTab.Upload, duringDialog);
        s.Host.Press(Key.F11);
        Assert.AreEqual(ShellTab.Settings, CurrentOf(s));
    }

    [TestMethod, Timeout(60000)]
    public void Page_keys_reach_the_page_while_a_TableView_is_focused()
    {
        var s = Start();
        StringAssert.Contains(s.Host.FocusPath, "TableView");

        s.Host.Press(Key.R);
        s.Host.Press(Key.D1);

        CollectionAssert.AreEqual(new[] { Key.R, Key.D1 }, s.Probe.Handled);
    }

    [TestMethod, Timeout(60000)]
    public void Page_keys_do_not_reach_the_page_while_another_page_is_shown()
    {
        var s = Start();
        s.Host.Press(Key.F10);

        s.Host.Press(Key.R);

        Assert.IsEmpty(s.Probe.Handled);
    }

    [TestMethod, Timeout(60000)]
    public void Focus_survives_a_tab_switch_and_back()
    {
        var s = Start();
        Assert.Contains("TableView", s.Host.FocusPath);

        s.Host.Press(Key.F11);
        Assert.Contains("PageSidebar", s.Host.FocusPath);
        s.Host.Press(Key.F9);

        Assert.Contains("TableView", s.Host.FocusPath);
        s.Host.Press(Key.R);
        Assert.HasCount(1, s.Probe.Handled);
    }

    [TestMethod, Timeout(60000)]
    public void Clicking_a_tab_label_switches_the_page()
    {
        var s = Start();

        foreach (var (name, expected) in new[] { ("F10 History", ShellTab.History), ("F12 Help", ShellTab.Help), ("F11 Settings", ShellTab.Settings), ("F9 Upload", ShellTab.Upload) })
        {
            var column = s.Host.Lines[0].IndexOf(name, StringComparison.Ordinal);
            Assert.IsGreaterThanOrEqualTo(0, column, s.Host.Screen);
            s.Host.Click(column + 1, 0);
            Assert.AreEqual(expected, CurrentOf(s), name);
        }
    }

    [TestMethod, Timeout(60000)]
    public void Below_80x24_the_overlay_shows_and_keys_do_nothing()
    {
        var s = Start();

        s.Host.Resize(70, 20);
        s.Host.WaitUntil(() => s.Shell.OverlayVisible, "overlay");
        StringAssert.Contains(s.Host.Screen, "at least 80x24");
        s.Host.Press(Key.F10);
        s.Host.Press(Key.R);

        Assert.AreEqual(ShellTab.Upload, CurrentOf(s));
        Assert.IsEmpty(s.Probe.Handled);
        s.Host.Resize(100, 32);
        s.Host.WaitUntil(() => !s.Shell.OverlayVisible, "overlay gone");
        s.Host.Press(Key.F10);
        Assert.AreEqual(ShellTab.History, CurrentOf(s));
    }

    [TestMethod, Timeout(60000)]
    public void Opening_on_Settings_as_configure_does_gives_the_sidebar_the_focus()
    {
        var s = Start(ShellTab.Settings);

        Assert.AreEqual(ShellTab.Settings, CurrentOf(s));
        Assert.Contains("PageSidebar", s.Host.FocusPath);
        Assert.IsTrue(s.Host.Shows("Destination"), s.Host.Screen);
    }

    [TestMethod, Timeout(60000)]
    public void Unsaved_Settings_changes_show_a_badge_survive_tab_switches_and_move_the_save_targets_into_the_status_line()
    {
        var s = Start();
        s.Host.OnUi(() => s.Page.Field("Sftp:Port").Value = "2222");

        Assert.IsTrue(s.Host.Lines[0].Contains("Settings ●"), s.Host.Screen);
        s.Host.Press(Key.F11);
        s.Host.Press(Key.F9);
        s.Host.Press(Key.F11);

        Assert.AreEqual("2222", s.Page.Field("Sftp:Port").Value);
        Assert.IsTrue(s.Host.Shows("Machine Config: Sources, Destination; User: rest"), s.Host.Screen);
        Assert.IsFalse(s.Host.Shows("Settings | Sources"), "the header line moved into the status line");
    }

    [TestMethod, Timeout(60000)]
    public void Ctrl_Q_with_unsaved_Settings_changes_asks_and_Cancel_keeps_the_TUI_running()
    {
        var s = Start();
        s.Host.OnUi(() => s.Page.Field("Sftp:Port").Value = "2222");

        s.Host.Press(Key.Q.WithCtrl);
        s.Host.Press(Key.C.WithCtrl);

        Assert.HasCount(2, s.Dialogs.UnsavedAsked);
        Assert.IsFalse(s.Host.Stopped.IsSet);
        Assert.IsTrue(s.Page.HasChanges);
    }

    [TestMethod, Timeout(60000)]
    public void Discard_quits_with_exit_code_0_and_saves_nothing()
    {
        var s = Start();
        s.Dialogs.UnsavedAnswers.Enqueue(UnsavedChoice.Discard);
        s.Host.OnUi(() => s.Page.Field("Sftp:Port").Value = "2222");
        var before = File.ReadAllText(MachinePath);

        s.Host.Press(Key.Q.WithCtrl);

        Assert.IsTrue(s.Host.Stopped.Wait(TimeSpan.FromSeconds(10)));
        Assert.AreEqual(0, s.Shell.ExitCode);
        Assert.AreEqual(before, File.ReadAllText(MachinePath));
    }

    [TestMethod, Timeout(60000)]
    public void Ctrl_Q_without_changes_quits_at_once()
    {
        var s = Start();

        s.Host.Press(Key.Q.WithCtrl);

        Assert.IsTrue(s.Host.Stopped.Wait(TimeSpan.FromSeconds(10)));
        Assert.IsEmpty(s.Dialogs.UnsavedAsked);
    }

    [TestMethod, Timeout(60000)]
    public void Terminate_exits_130_without_asking_or_saving()
    {
        var s = Start();
        s.Host.OnUi(() => s.Page.Field("Sftp:Port").Value = "2222");

        s.Host.OnUi(() => s.Shell.Terminate());

        Assert.IsTrue(s.Host.Stopped.Wait(TimeSpan.FromSeconds(10)));
        Assert.AreEqual(ExitCodes.Cancelled, s.Shell.ExitCode);
        Assert.IsEmpty(s.Dialogs.UnsavedAsked);
    }
}

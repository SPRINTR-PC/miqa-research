using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using MiresSftpUploader.Core;
using MiresSftpUploader.ViewModels;
using Terminal.Gui.App;
using Terminal.Gui.Drawing;
using Terminal.Gui.Input;
using Terminal.Gui.ViewBase;
using Terminal.Gui.Views;

namespace MiresSftpUploader.SettingsTui;

/// <summary>
/// The Settings TUI's screen: header, sidebar of pages, the selected page's content, status line and key bar, plus the keys that work everywhere
/// (Ctrl+S Save, Ctrl+R Revert, Ctrl+Q Quit, F4 Issues, Ctrl+PageUp/PageDown between pages, Esc one focus level out).
/// Below 80x24 an overlay replaces the screen. It drives one <see cref="SettingsPageViewModel"/> and never runs a modal loop itself:
/// questions go through <see cref="ITuiDialogs"/>.
/// </summary>
public sealed class SettingsTuiWindow : Window
{
    private readonly IApplication _app;
    private readonly SettingsPageViewModel _vm;
    private readonly ITuiDialogs _dialogs;
    private readonly PageCatalog _catalog;
    private readonly IReadOnlyList<PageDefinition> _pages;
    private readonly Label _header = new() { X = 0, Y = 0, Width = Dim.Fill() };
    private readonly PageSidebar _sidebar;
    private readonly FrameView _body = new() { Y = 1, Width = Dim.Fill(), Height = Dim.Fill(2), BorderStyle = LineStyle.Single };
    private readonly Label _status = new() { X = 0, Y = Pos.AnchorEnd(2), Width = Dim.Fill() };
    private readonly Label _keyBar = new() { X = 0, Y = Pos.AnchorEnd(1), Width = Dim.Fill() };
    private readonly Label _overlay = new() { X = 0, Y = 0, Width = Dim.Fill(), Height = Dim.Fill(), Visible = false };
    private readonly List<(Key Key, string Label, Action Action)> _commands = [];
    private readonly List<SettingFieldViewModel> _hooked = [];
    private readonly bool _hosted;
    private int _shown = -1;
    private bool _refreshing;

    /// <param name="hosted">
    /// Inside the whole-app shell: no header, status line, key bar or size overlay of its own (the shell shows <see cref="StatusText"/>
    /// and <see cref="KeyHints"/>), the sidebar and body use the full height, and the window does not take the focus when it is initialised.
    /// </param>
    public SettingsTuiWindow(IApplication app, SettingsPageViewModel vm, ITuiDialogs dialogs, PageCatalog? catalog = null, bool hosted = false)
    {
        _hosted = hosted;
        _app = app;
        _vm = vm;
        _dialogs = dialogs;
        PostToUi = action => app.Invoke(action);
        _catalog = catalog ?? PageCatalog.CreateDefault();
        _pages = _catalog.Pages;
        Title = "MIRES SFTP Uploader - Settings";
        BorderStyle = LineStyle.None;
        SetScheme(Theme.Base);
        _header.SetScheme(Theme.Header);
        _keyBar.SetScheme(Theme.Bar);
        _body.SetScheme(Theme.Pane);
        _overlay.SetScheme(Theme.Error);
        _overlay.TextAlignment = Alignment.Center;
        _overlay.VerticalTextAlignment = Alignment.Center;

        vm.Confirm = (title, message) => Task.FromResult(dialogs.Confirm(title, message));
        _sidebar = new PageSidebar(_pages, vm);
        _body.X = Pos.Right(_sidebar);
        if (hosted)
        {
            _sidebar.Y = 0;
            _sidebar.Height = Dim.Fill();
            _body.Y = 0;
            _body.Height = Dim.Fill();
            foreach (var v in new View[] { _header, _status, _keyBar, _overlay }) v.Visible = false;
        }

        AddCommand(Key.S.WithCtrl, "Ctrl+S Save", Save);
        AddCommand(Key.R.WithCtrl, "Ctrl+R Revert", Revert);
        AddCommand(Key.F4, "F4 Issues", ShowIssues);
        AddCommand(Key.F5, "F5 Check", CheckConnection);
        AddCommand(Key.Q.WithCtrl, "Ctrl+Q Quit", Quit);

        Add(_header, _sidebar, _body, _status, _keyBar, _overlay);
        _sidebar.ValueChanged += (_, _) => ShowPage();
        _sidebar.Accepting += (_, e) => { EnterPage(); e.Handled = true; };
        _sidebar.KeyDown += (_, k) =>
        {
            if (k != Key.CursorRight && k != Key.Tab) return;
            EnterPage();
            k.Handled = true;
        };
        KeyDown += OnKey;
        FrameChanged += (_, _) => CheckSize();
        Initialized += (_, _) =>
        {
            // Visible inside a host, a focus change here mutates the subview list while the host is still in EndInit.
            if (_hosted) return;
            _sidebar.SetFocus();
            CheckSize();
        };

        _vm.PropertyChanged += OnVmChanged;
        _vm.Saved += Rebuild;
        _vm.Sources.CollectionChanged += (_, _) => Refresh();
        ShowPage();
    }

    /// <summary>The process exit code once the window has stopped: 0, or 130 after <see cref="Terminate"/>.</summary>
    public int ExitCode { get; private set; } = ExitCodes.Ok;

    /// <summary>True once Quit (or <see cref="Terminate"/>) asked the application to stop.</summary>
    public bool ExitRequested { get; private set; }

    public SettingsPageViewModel Page => _vm;

    public int PageIndex
    {
        get => _sidebar.SelectedItem ?? 0;
        set => _sidebar.SelectedItem = Math.Clamp(value, 0, _pages.Count - 1);
    }

    public PageSidebar Sidebar => _sidebar;

    /// <summary>The frame holding the selected page's content.</summary>
    public FrameView Body => _body;

    public string StatusText => _status.Text;

    /// <summary>The keys of this page for a host's key bar (the host adds its own Quit).</summary>
    public string KeyHints => string.Join("   ", _commands.Where(c => c.Key != Key.Q.WithCtrl).Select(c => c.Label)) + "   Ctrl+PgUp/PgDn Page   Esc Back";

    /// <summary>Raised after the status text, badges or header changed (a host redraws its own chrome).</summary>
    public event Action? ChromeChanged;

    /// <summary>Quit as the Quit key does: asks about unsaved changes, then stops the application.</summary>
    public void RequestQuit() => Quit();

    public bool OverlayVisible => _overlay.Visible;

    /// <summary>Adds a key that works on every page and a label in the key bar (a page ticket's way to add, say, F5 Check).</summary>
    public void AddCommand(Key key, string label, Action action)
    {
        _commands.Add((key, label, action));
        _keyBar.Text = string.Join("   ", _commands.Select(c => c.Label)) + "   Ctrl+PgUp/PgDn Page   Esc Back";
    }

    /// <summary>Redraws the header, status line and sidebar badges. Pages call it after changing something the badges depend on.</summary>
    public void RefreshChrome() => Refresh();

    /// <summary>SIGHUP or SIGTERM: stop with exit code 130 and write nothing.</summary>
    public void Terminate()
    {
        ExitCode = ExitCodes.Cancelled;
        Stop();
    }

    private void Stop()
    {
        ExitRequested = true;
        _app.RequestStop();
    }

    // ---------------------------------------------------------------- keys

    private void OnKey(object? sender, Key k)
    {
        if (_overlay.Visible) return;
        foreach (var (key, _, action) in _commands)
        {
            if (k != key) continue;
            action();
            k.Handled = true;
            return;
        }

        if (k == Key.PageDown.WithCtrl || k == Key.PageUp.WithCtrl)
        {
            PageIndex += k == Key.PageDown.WithCtrl ? 1 : -1;
            k.Handled = true;
        }
        else if (k == Key.Esc)
        {
            FocusLevels.Back(_body, _sidebar);
            k.Handled = true;
        }
    }

    private void EnterPage()
    {
        if (_body.SubViews.FirstOrDefault() is { } content) FocusLevels.FocusFirstInput(content);
    }

    // ---------------------------------------------------------------- commands

    private void Save()
    {
        if (!_vm.HasChanges || _vm.HasErrors) return;
        _vm.SaveCommand.Fire(ShowError);
        Refresh();
    }

    private void Revert()
    {
        _vm.RevertCommand.Fire(ShowError);
        Rebuild();
    }

    /// <summary>
    /// Checks the saved configuration (F5): one session, host key and credentials, no upload. Null means this window cannot check
    /// (tests install a checker on a <c>FakeRemote</c>; the application installs the real one).
    /// </summary>
    public Func<CancellationToken, Task<ConnectionCheckResult>>? ConnectionChecker { get; set; }

    /// <summary>Hides Secret values in text from a failed check before it is shown. The application installs one built from the Secret Store.</summary>
    public Func<string, string> Redact { get; set; } = text => text;

    /// <summary>Runs an action on the UI thread. Tests replace it with a direct call because their harness has no running loop.</summary>
    public Action<Action> PostToUi { get; set; }

    /// <summary>The check in flight, or a completed task. Completes after its result dialog was shown.</summary>
    public Task PendingCheck { get; private set; } = Task.CompletedTask;

    private void CheckConnection()
    {
        const string title = "Check connection";
        if (_vm.HasChanges)
        {
            _dialogs.ShowMessage(title, "Save first (Ctrl+S): the check uses the saved configuration, not the unsaved changes.");
            return;
        }

        if (!PendingCheck.IsCompleted) return;
        if (ConnectionChecker is not { } checker)
        {
            _dialogs.ShowMessage(title, "The connection check is not available.");
            return;
        }

        PendingCheck = Task.Run(async () =>
        {
            string message;
            try
            {
                message = Redact((await checker(CancellationToken.None).ConfigureAwait(false)).Message);
            }
            catch (Exception e)
            {
                message = Redact($"Connection check failed: {e.Message}");
            }

            PostToUi(() => _dialogs.ShowMessage(title, message));
        });
    }

    /// <summary>Tells the user that a command failed (the message passes the redactor); the interface keeps running.</summary>
    public void ShowError(Exception error) => _dialogs.ShowMessage("Error", Redact(error.Message));

    private void ShowIssues() => _dialogs.ShowIssues(IssueList.All(_vm));

    private void Quit()
    {
        if (_vm.HasChanges)
        {
            switch (_dialogs.AskUnsaved(canSave: !_vm.HasErrors))
            {
                case UnsavedChoice.Cancel:
                    return;
                case UnsavedChoice.Save:
                    Save();
                    if (_vm.HasChanges) return; // the save failed: stay and show why
                    break;
            }
        }

        Stop();
    }

    // ---------------------------------------------------------------- pages

    private void ShowPage()
    {
        var index = PageIndex;
        if (index == _shown) return;
        _shown = index;
        Rebuild();
    }

    /// <summary>Builds the selected page again, after the view models were reloaded (Save, Revert) or the page's shape changed.</summary>
    private void Rebuild()
    {
        if (_shown < 0) return;
        var inBody = _body.HasFocus;
        foreach (var old in _body.SubViews.ToList()) { _body.Remove(old); old.Dispose(); }
        var page = _pages[_shown];
        _body.Title = page.Title;
        var content = page.Build(new PageContext(_app, _vm, _dialogs, Refresh));
        _body.Add(content);
        foreach (var f in _hooked) f.PropertyChanged -= OnFieldChanged;
        _hooked.Clear();
        foreach (var f in _vm.Fields) { f.PropertyChanged += OnFieldChanged; _hooked.Add(f); }
        if (inBody) FocusLevels.FocusFirstInput(content);
        Refresh();
    }

    private void OnVmChanged(object? sender, PropertyChangedEventArgs e) => Refresh();

    private void OnFieldChanged(object? sender, PropertyChangedEventArgs e) => Refresh();

    // ---------------------------------------------------------------- chrome

    private void Refresh()
    {
        if (_refreshing) return;
        _refreshing = true;
        try
        {
            var errors = IssueList.Errors(_vm).Count;
            _header.Text = _vm.HasDataDirectoryProblem
                ? "✗ The Data Directory cannot be used: no Run can start. See the Data Directory page."
                : "Settings | Sources, Destination: Machine Config; the rest: User Overrides";
            _header.SetScheme(_vm.HasDataDirectoryProblem ? Theme.Error : Theme.Header);
            var parts = new List<string>
            {
                _vm.HasChanges ? "● unsaved changes" : "no changes",
                errors > 0 ? $"✗ {errors} problem(s): Save is disabled (F4 lists them)"
                    : _vm.Warnings.Count > 0 ? $"! {_vm.Warnings.Count} warning(s) (F4)" : "valid",
            };
            if (_vm.SaveMessage.Length > 0) parts.Add(_vm.SaveMessage);
            if (_hosted && _vm.HasDataDirectoryProblem) parts.Insert(0, "✗ The Data Directory cannot be used: no Run can start (Data Directory page)");
            _status.Text = string.Join("   |   ", parts);
            _status.SetScheme(errors > 0 ? Theme.Error : _vm.HasChanges ? Theme.Locked : Theme.Ok);
            _sidebar.RefreshBadges(_vm);
            SetNeedsDraw();
            ChromeChanged?.Invoke();
        }
        finally
        {
            _refreshing = false;
        }
    }

    private void CheckSize()
    {
        if (_hosted) return;
        var small = Frame.Width < SettingsTuiEntry.MinimumWidth || Frame.Height < SettingsTuiEntry.MinimumHeight;
        _overlay.Text = $"The terminal is {Frame.Width}x{Frame.Height}; the Settings TUI needs at least " +
                        $"{SettingsTuiEntry.MinimumWidth}x{SettingsTuiEntry.MinimumHeight}. Make the window larger.";
        _overlay.Visible = small;
        foreach (var v in new View[] { _header, _sidebar, _body, _status, _keyBar }) v.Visible = !small;
    }

    protected override void Dispose(bool disposing)
    {
        if (disposing)
        {
            _vm.PropertyChanged -= OnVmChanged;
            _vm.Saved -= Rebuild;
            foreach (var f in _hooked) f.PropertyChanged -= OnFieldChanged;
        }

        base.Dispose(disposing);
    }
}

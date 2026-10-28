using System;
using System.Linq;
using System.Text;
using MiresSftpUploader.Core;
using MiresSftpUploader.SettingsTui;
using MiresSftpUploader.ViewModels;
using Terminal.Gui.App;
using Terminal.Gui.Drawing;
using Terminal.Gui.Input;
using Terminal.Gui.ViewBase;
using Terminal.Gui.Views;

namespace MiresSftpUploader.Tui;

/// <summary>
/// The whole-app TUI: a tab bar (Upload, History, Settings, Help; F9-F12 or a click), one page at a time, and one status line and key bar shared
/// by all pages. The Settings page is the <see cref="SettingsTuiWindow"/> in hosted mode. Page keys are routed here through the application's
/// keyboard, scoped to the current page and to this window (not a dialog) holding the focus, because a focused table or list swallows
/// letters and digits for its own type-to-search. Below 80x24 an overlay replaces the screen and keys do nothing.
/// </summary>
public sealed class TuiShell : Window
{
    public const string SaveTargetsNote = "Machine Config: Sources, Destination; User: rest";

    private static readonly string[] TabNames = ["Upload", "History", "Settings", "Help"];
    private static readonly Key[] TabKeys = [Key.F9, Key.F10, Key.F11, Key.F12];
    private static readonly Rune NoHotKey = new('￿');

    private readonly IApplication _app;
    private readonly ITuiDialogs _dialogs;
    private readonly SettingsPageViewModel _settings;
    private readonly SettingsTuiWindow _settingsWindow;
    private readonly IShellPage _upload;
    private readonly IShellPage _history;
    private readonly IShellPage _help;
    private readonly View[] _pages = new View[4];
    private readonly Label[] _tabs = new Label[4];
    private readonly View _tabBar = new() { X = 0, Y = 0, Width = Dim.Fill(), Height = 1 };

    // A plain View has CanFocus = false, which stops focus reaching anything inside it.
    private readonly View _area = new() { CanFocus = true, X = 0, Y = 1, Width = Dim.Fill(), Height = Dim.Fill(2) };
    private readonly Label _status = new() { X = 0, Y = Pos.AnchorEnd(2), Width = Dim.Fill(), HotKeySpecifier = NoHotKey };
    private readonly Label _keyBar = new() { X = 0, Y = Pos.AnchorEnd(1), Width = Dim.Fill(), HotKeySpecifier = NoHotKey };
    private readonly Label _overlay = new() { X = 0, Y = 0, Width = Dim.Fill(), Height = Dim.Fill(), Visible = false, HotKeySpecifier = NoHotKey };
    private bool _wasSmall;

    /// <param name="start">The page to open on: Upload for <c>--tui</c>, Settings for <c>--configure</c> and for an invalid configuration.</param>
    /// <param name="upload">The Upload page; null shows a placeholder (tests install a probe).</param>
    public TuiShell(IApplication app, SettingsPageViewModel settings, ITuiDialogs dialogs, ShellTab start = ShellTab.Upload,
        IShellPage? upload = null, IShellPage? history = null, IShellPage? help = null)
    {
        _app = app;
        _dialogs = dialogs;
        _settings = settings;
        Current = start;
        Title = "MIRES SFTP Uploader";
        BorderStyle = LineStyle.None;
        SetScheme(Theme.Base);
        _keyBar.SetScheme(Theme.Bar);
        _overlay.SetScheme(Theme.Error);
        _overlay.TextAlignment = Alignment.Center;
        _overlay.VerticalTextAlignment = Alignment.Center;
        _tabBar.SetScheme(Theme.Header);
        _area.SetScheme(Theme.Base);

        _upload = upload ?? new PlaceholderPage("Upload");
        _history = history ?? new PlaceholderPage("History");
        _help = help ?? new PlaceholderPage("Help");
        _settingsWindow = new SettingsTuiWindow(app, settings, dialogs, hosted: true);
        _pages[0] = (View)_upload;
        _pages[1] = (View)_history;
        _pages[2] = _settingsWindow;
        _pages[3] = (View)_help;
        foreach (var page in _pages)
        {
            page.X = 0;
            page.Y = 0;
            page.Width = Dim.Fill();
            page.Height = Dim.Fill();
            page.Visible = false;
            _area.Add(page);
        }

        for (var i = 0; i < 4; i++)
        {
            var label = new Label { Y = 0, Height = 1, HotKeySpecifier = NoHotKey };
            var target = (ShellTab)i;
            // A Label has no click action of its own.
            label.MouseEvent += (_, e) =>
            {
                if (!e.Flags.HasFlag(MouseFlags.LeftButtonClicked)) return;
                if (!_overlay.Visible) Show(target);
                e.Handled = true;
            };
            _tabs[i] = label;
            _tabBar.Add(label);
        }

        Add(_tabBar, _area, _status, _keyBar, _overlay);
        _app.Keyboard.KeyDown += OnAppKey;
        FrameChanged += (_, _) => CheckSize();
        _settingsWindow.ChromeChanged += Refresh;
        foreach (var page in new[] { _upload, _history, _help }) page.ChromeChanged += Refresh;
        Initialized += (_, _) =>
        {
            CheckSize();
            // The first page is shown in the loop's first iteration, not here: pages made visible during initialisation do not take the focus
            // (the application then puts it on the page area), and a focus change in EndInit changes the subview list being enumerated.
            EventHandler<EventArgs<IApplication?>>? once = null;
            once = (_, _) =>
            {
                _app.Iteration -= once;
                if (!_overlay.Visible) ShowCurrent();
            };
            _app.Iteration += once;
        };
    }

    public ShellTab Current { get; private set; }

    public bool OverlayVisible => _overlay.Visible;

    public SettingsTuiWindow SettingsWindow => _settingsWindow;

    public string StatusText => _status.Text;

    public string KeyBarText => _keyBar.Text;

    /// <summary>0 after a user quit, 130 after <see cref="Terminate"/>.</summary>
    public int ExitCode => _settingsWindow.ExitCode;

    /// <summary>How long a quit or a signal waits for a cancelled Run to end before the TUI exits anyway (a Run cut off is an Abandoned Run).</summary>
    public TimeSpan CancelWait { get; set; } = TimeSpan.FromSeconds(10);

    private bool IsRunActive => _upload.IsRunActive || _history.IsRunActive;

    private bool _stopping;
    private bool _signalled;

    /// <summary>
    /// Quit (Ctrl+Q, Ctrl+C): asks about an active Run first ("Cancel the Run and quit" or "Back"), then about unsaved Settings changes (Save,
    /// Discard, Cancel); only when both are settled does it cancel the Run, wait up to <see cref="CancelWait"/>, and stop with exit code 0.
    /// </summary>
    public void RequestQuit()
    {
        if (_stopping) return;
        var running = IsRunActive;
        if (running && !_dialogs.AskCancelRunAndQuit()) return;
        if (!_settingsWindow.ResolveUnsaved()) return;
        if (running) CancelRunsThen(() => _settingsWindow.StopNow());
        else _settingsWindow.StopNow();
    }

    /// <summary>
    /// SIGHUP or SIGTERM: cancel an active Run, wait up to <see cref="CancelWait"/>, then stop with exit code 130; nothing is asked or saved.
    /// A second signal stops at once.
    /// </summary>
    public void Terminate()
    {
        if (_signalled || !IsRunActive)
        {
            _signalled = true;
            _settingsWindow.Terminate();
            return;
        }

        _signalled = true;
        CancelRunsThen(_settingsWindow.Terminate);
    }

    private void CancelRunsThen(Action stop)
    {
        _stopping = true;
        _upload.CancelRun();
        _history.CancelRun();
        _statusOverride = "Cancelling…";
        Refresh();
        var deadline = DateTime.UtcNow + CancelWait;
        _app.AddTimeout(TimeSpan.FromMilliseconds(50), () =>
        {
            if (_settingsWindow.ExitRequested) return false;
            if (IsRunActive && DateTime.UtcNow < deadline) return true;
            stop();
            return false;
        });
    }

    private string? _statusOverride;

    /// <summary>
    /// Retry from the History page: switches to Upload and starts the Retry Run at once. While a Run is active nothing switches and the result is
    /// a notice for History; otherwise the task ends with the Run and the result is null (a refusal by the Run-lock shows on Upload).
    /// </summary>
    public async System.Threading.Tasks.Task<string?> RetryFromHistoryAsync(Guid runId, UploadPageViewModel upload)
    {
        if (upload.IsRunning) return UploadPageViewModel.RunActiveNotice;
        Show(ShellTab.Upload);
        await upload.RetryRunAsync(runId);
        return null;
    }

    public void Show(ShellTab tab)
    {
        Current = tab;
        ShowCurrent();
    }

    private void ShowCurrent()
    {
        for (var i = 0; i < 4; i++) _pages[i].Visible = i == (int)Current && !_overlay.Visible;
        Refresh();
        FocusPage();
        SetNeedsLayout();
        SetNeedsDraw();
    }

    // ---------------------------------------------------------------- keys

    private void OnAppKey(object? sender, Key key)
    {
        if (!FocusInShell()) return;
        if (key == Key.Q.WithCtrl || key == Key.C.WithCtrl)
        {
            RequestQuit();
            key.Handled = true;
            return;
        }

        if (_overlay.Visible)
        {
            key.Handled = true;
            return;
        }

        var index = Array.IndexOf(TabKeys, key);
        if (index >= 0)
        {
            Show((ShellTab)index);
            key.Handled = true;
            return;
        }

        if (PageOf(Current) is { } page && page.HandleKey(key)) key.Handled = true;
    }

    private IShellPage? PageOf(ShellTab tab) => tab switch
    {
        ShellTab.Upload => _upload,
        ShellTab.History => _history,
        ShellTab.Help => _help,
        _ => null,
    };

    /// <summary>True while this window, and not a dialog on top of it, has the focus.</summary>
    private bool FocusInShell()
    {
        var focused = _app.Navigation?.GetFocused();
        if (focused is null) return true;
        for (var v = focused; v is not null; v = v.SuperView)
            if (v == this) return true;
        return false;
    }

    private bool PageHasFocus()
    {
        for (var v = _app.Navigation?.GetFocused(); v is not null; v = v.SuperView)
            if (v == _pages[(int)Current]) return true;
        return false;
    }

    private void FocusPage()
    {
        if (!IsInitialized) return;
        if (Current == ShellTab.Settings) _settingsWindow.Sidebar.SetFocus();
        else PageOf(Current)?.FocusDefault();
    }

    // ---------------------------------------------------------------- chrome

    private string TabText(int i)
    {
        var badge = (ShellTab)i switch
        {
            ShellTab.Settings => _settings.HasChanges ? " ●" : "",
            ShellTab.Upload => _upload.Badge is { Length: > 0 } b ? " " + b : "",
            _ => "",
        };
        return $" F{i + 9} {TabNames[i]}{badge} ";
    }

    private void Refresh()
    {
        var x = 0;
        for (var i = 0; i < 4; i++)
        {
            _tabs[i].Text = TabText(i);
            _tabs[i].X = x;
            _tabs[i].Width = _tabs[i].Text.Length;
            _tabs[i].SetScheme(i == (int)Current ? Theme.Nav : Theme.Header);
            x += _tabs[i].Text.Length + 1;
        }

        var onSettings = Current == ShellTab.Settings;
        var status = onSettings ? WithSaveTargets(_settingsWindow.StatusText) : PageOf(Current)?.StatusText ?? "";
        if (_statusOverride is not null) status = _statusOverride;
        else if (IsRunActive) status += "   Settings changes apply to the next Run";
        _status.Text = status;
        _status.SetScheme(onSettings && _settings.HasChanges ? Theme.Locked : Theme.Ok);
        var pageKeys = onSettings ? _settingsWindow.KeyHints : PageOf(Current)?.KeyHints ?? "";
        _keyBar.Text = string.Join("   ", new[] { pageKeys, "F9-F12 Page", "Ctrl+Q Quit" }.Where(t => t.Length > 0));
        SetNeedsDraw();
    }

    /// <summary>The shipped Settings header moves into the status line after the state; it is dropped first when the line is too long.</summary>
    private string WithSaveTargets(string status)
    {
        var full = $"{status}   |   {SaveTargetsNote}";
        return full.Length <= Math.Max(Frame.Width, 1) ? full : status;
    }

    private void CheckSize()
    {
        var small = Frame.Width < SettingsTuiEntry.MinimumWidth || Frame.Height < SettingsTuiEntry.MinimumHeight;
        _overlay.Text = $"The terminal is {Frame.Width}x{Frame.Height}; the TUI needs at least " +
                        $"{SettingsTuiEntry.MinimumWidth}x{SettingsTuiEntry.MinimumHeight}. Make the window larger.";
        var was = _wasSmall;
        _wasSmall = small;
        _overlay.Visible = small;
        foreach (var v in new View[] { _tabBar, _area, _status, _keyBar }) v.Visible = !small;
        if (!small && was)
        {
            ShowCurrent();
        }
        else if (small) foreach (var page in _pages) page.Visible = false;
        if (!small) Refresh();
    }

    protected override void Dispose(bool disposing)
    {
        if (disposing) _app.Keyboard.KeyDown -= OnAppKey;
        base.Dispose(disposing);
    }
}

using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.ComponentModel;
using System.Linq;
using System.Text;
using MiresSftpUploader.SettingsTui;
using MiresSftpUploader.ViewModels;
using ReactiveUI;
using Terminal.Gui.App;
using Terminal.Gui.Drawing;
using Terminal.Gui.Input;
using Terminal.Gui.ViewBase;
using Terminal.Gui.Views;

namespace MiresSftpUploader.Tui;

/// <summary>
/// The Upload page of the whole-app TUI on the real <see cref="UploadPageViewModel"/> (and <see cref="LogPaneViewModel"/>), in the "Split" layout:
/// a 27-column left column (Sources, the four filters as checkboxes, the commands) next to the progress line and the file table; a banner row when
/// no Run can start; the Log pane as a toggled bottom pane. The status text and key hints go to the shell. Page keys come from the shell:
/// R Run, D Dry run, S Scan, X Cancel, T retry failed, 1-4 filters, L Log, End follow (Space includes the Source under the cursor).
/// </summary>
public sealed class UploadTuiPage : View, IShellPage
{
    public const int LeftWidth = 27;
    public const int LogRows = 8;

    /// <summary>What is left of the 80-column key bar after the shell's own "F9-F12 Page" and "Ctrl+Q Quit".</summary>
    private const int HintBudget = 50;

    private static readonly Rune NoHotKey = new('￿');

    private readonly IApplication _app;
    private readonly UploadPageViewModel _vm;
    private readonly LogPaneViewModel? _log;
    private readonly ITuiDialogs _dialogs;
    private readonly TableView _table = new() { FullRowSelect = true, MultiSelect = false };
    private readonly ProgressBar _bar = new() { ProgressBarFormat = ProgressBarFormat.SimplePlusPercentage };
    private readonly ObservableCollection<string> _sourceItems = [];
    private readonly ListView _sources;
    private readonly Label _summary = new() { HotKeySpecifier = NoHotKey };
    private readonly Label _banner = new() { HotKeySpecifier = NoHotKey, Height = 0 };
    private readonly CheckBox[] _filters = [new(), new(), new(), new()];
    private readonly FileFilter[] _filterFlags = [FileFilter.Succeeded, FileFilter.Failed, FileFilter.Skipped, FileFilter.Pending];
    private readonly Button[] _buttons = new Button[5];
    private readonly bool[] _commandCan = new bool[5];
    private readonly ListView? _logList;
    private readonly FrameView _logFrame = new() { Title = "Log", BorderStyle = LineStyle.Single, Visible = false };
    private bool _showLog;
    private bool _syncing;
    private bool _refreshPending;
    private bool _disposed;
    private string _lastLockRefusal = "";

    public UploadTuiPage(IApplication app, UploadPageViewModel vm, LogPaneViewModel? log, ITuiDialogs dialogs)
    {
        _app = app;
        _vm = vm;
        _log = log;
        _dialogs = dialogs;
        CanFocus = true;

        _table.Table = new FileRowsSource(vm.Files);
        _table.Style.AlwaysShowHeaders = true;
        _table.Style.ShowHorizontalHeaderOverline = false;
        _table.Style.ExpandLastColumn = true;
        _table.Style.ColumnStyles[0] = new ColumnStyle { MinWidth = 1, MaxWidth = 1 };
        _table.Style.ColumnStyles[1] = new ColumnStyle { MinWidth = 6, MaxWidth = 14 };
        _table.Style.ColumnStyles[2] = new ColumnStyle { MinWidth = 12, MaxWidth = 30 };
        _table.SetScheme(Theme.Pane);
        // The mouse wheel and the cursor keys move the cursor: that is a manual move, which ends follow mode.
        _table.ValueChanged += (_, _) =>
        {
            if (!_syncing) _vm.IsFollowing = false;
        };

        _sources = new ListView { Source = new ListWrapper<string>(_sourceItems), CanFocus = true };
        _sources.SetScheme(Theme.Nav);
        _sources.Accepting += (_, e) =>
        {
            ToggleSource();
            e.Handled = true;
        };
        _sources.KeyDown += (_, k) =>
        {
            if (k != Key.Space) return;
            ToggleSource();
            k.Handled = true;
        };

        _bar.SetScheme(Theme.Ok);
        _summary.SetScheme(Theme.Base);
        _banner.SetScheme(Theme.Error);

        var names = new[] { "Run", "Dry run", "Scan", "Cancel", "Retry failed" };
        var commands = new[] { vm.StartCommand, vm.DryRunCommand, vm.ScanCommand, vm.CancelCommand, vm.RetryFailedCommand };
        for (var i = 0; i < 5; i++)
        {
            var command = commands[i];
            var index = i;
            var button = new Button { Text = names[i], NoPadding = true, ShadowStyle = ShadowStyles.None, HotKeySpecifier = NoHotKey };
            button.Accepting += (_, e) =>
            {
                Fire(index);
                e.Handled = true;
            };
            command.CanExecute.Subscribe(can =>
            {
                _commandCan[index] = can;
                button.Enabled = Allowed(index);
            });
            _buttons[i] = button;
        }

        for (var i = 0; i < 4; i++)
        {
            var flag = _filterFlags[i];
            var box = _filters[i];
            box.HotKeySpecifier = NoHotKey;
            // A mouse click flips the CheckBox itself and never raises Accepting; follow the box whenever it disagrees with the view model.
            box.ValueChanged += (_, _) =>
            {
                if (!_syncing && (box.Value == CheckState.Checked) != _vm.Filter.HasFlag(flag)) Toggle(flag);
            };
            box.Accepting += (_, e) =>
            {
                Toggle(flag);
                e.Handled = true;
            };
        }

        if (log is not null)
        {
            _logList = new ListView { Source = new LogLinesSource(log.Entries), X = 0, Y = 0, Width = Dim.Fill(), Height = Dim.Fill(), CanFocus = false };
            _logList.SetScheme(Theme.Help);
            _logFrame.Add(_logList);
            log.Entries.CollectionChanged += (_, _) =>
            {
                if (_showLog) RequestRefresh();
            };
        }

        vm.PropertyChanged += OnVmChanged;
        vm.Files.CollectionChanged += (_, _) => RequestRefresh();
        _vm.Refresh();
        Build();
        RefreshAll();
    }

    public event Action? Changed;

    public UploadPageViewModel Vm => _vm;

    public TableView Table => _table;

    public bool ShowLog => _showLog;

    public string StatusText => (_vm.IsRunning ? "▶ " : "") + _vm.Status;

    public string Badge => _vm.IsRunning ? $"▶ {(int)Math.Clamp(_vm.OverallProgress, 0, 100)}%" : "";

    public bool IsRunActive => _vm.IsRunning;

    public void CancelRun() => _vm.CancelCommand.Fire(Report);

    /// <summary>The page's keys, trimmed from the end to fit what the 80-column key bar has left.</summary>
    public string KeyHints
    {
        get
        {
            var parts = new List<string>();
            if (_vm.IsRunning) parts.Add("X Cancel");
            else parts.AddRange(["R Run", "D Dry", "S Scan"]);
            if (!_vm.IsFollowing) parts.Add("End Follow");
            if (!_vm.IsRunning && _vm.CanRetry) parts.Add("T Retry");
            parts.AddRange(["1-4 Filter", "L Log"]);
            var text = "";
            foreach (var part in parts)
            {
                var next = text.Length == 0 ? part : text + "  " + part;
                if (next.Length > HintBudget) break;
                text = next;
            }

            return text;
        }
    }

    /// <summary>The table gets the focus: a rebuild removes and re-adds views, which otherwise leaves nothing focused.</summary>
    public void FocusDefault()
    {
        if (IsInitialized && Visible) _table.SetFocus();
    }

    // ---------------------------------------------------------------- state

    /// <summary>Everything that changes during a Run, redrawn once per burst of changes.</summary>
    public void RefreshAll()
    {
        _refreshPending = false;
        if (_disposed) return;
        _syncing = true;
        try
        {
            var items = _vm.Sources.Select(s => $"{(s.Included ? "[x]" : "[ ]")} {s.Name}  {s.Summary}").ToList();
            ListSync.Update(_sourceItems, items);

            var counts = new[] { _vm.Succeeded, _vm.Failed, _vm.Skipped, _vm.Pending };
            var symbols = new[] { "✓", "✗", "⊘", "…" };
            for (var i = 0; i < 4; i++)
            {
                _filters[i].Text = $"{symbols[i]} {counts[i]}";
                _filters[i].Value = _vm.Filter.HasFlag(_filterFlags[i]) ? CheckState.Checked : CheckState.UnChecked;
            }

            var included = _vm.Sources.Count(s => s.Included);
            _summary.Text = $"Sources {included}/{_vm.Sources.Count}  →  {_vm.Destination}";
            var fraction = _vm.OverallProgress / 100.0;
            _bar.Fraction = double.IsNaN(fraction) ? 0 : (float)fraction;
            _banner.Text = BannerText();
            _banner.Height = _banner.Text.Length > 0 ? 1 : 0;
            for (var i = 0; i < 5; i++) _buttons[i].Enabled = Allowed(i);

            _table.Update();
            if (_vm.IsFollowing && _vm.Files.Count > 0)
            {
                _table.SetSelection(0, _vm.FollowIndex, false);
                _table.EnsureCursorIsVisible();
            }

            if (_logList is not null && _showLog && _log!.Entries.Count > 0)
            {
                _logList.SelectedItem = _log.Entries.Count - 1;
                _logList.EnsureSelectedItemVisible();
            }
        }
        finally
        {
            _syncing = false;
        }

        if (_vm.LockRefusal.Length > 0 && _vm.LockRefusal != _lastLockRefusal) ShowLockRefusal(_vm.LockRefusal);
        _lastLockRefusal = _vm.LockRefusal;
        SetNeedsLayout();
        SetNeedsDraw();
        Changed?.Invoke();
    }

    /// <summary>The reason no Run can start, shown on the page: Data Directory, configuration problems, or no Source included.</summary>
    private string BannerText()
    {
        if (_vm.IsBlocked) return $"✗ Uploading is disabled: {_vm.BlockedReason}";
        if (_vm.HasProblems)
            return $"✗ Configuration has {_vm.Problems.Split('\n', StringSplitOptions.RemoveEmptyEntries).Length} error(s); see Settings.";
        if (_vm.Sources.Count > 0 && _vm.Sources.All(s => !s.Included)) return "! Include at least one Source (Space on the Sources list).";
        return "";
    }

    private bool BannerBlocksStart => BannerText().Length > 0;

    private bool Allowed(int command) => _commandCan[command] && (command == 3 || !BannerBlocksStart);

    /// <summary>The refusal is a dialog the user dismisses (a modal opened from a timeout, outside the burst that raised it) as well as the status line.</summary>
    private void ShowLockRefusal(string text)
    {
        try
        {
            _app.AddTimeout(TimeSpan.FromMilliseconds(1), () =>
            {
                _dialogs.ShowMessage("Another Run is active", text);
                return false;
            });
        }
        catch (Exception)
        {
            // The application is shutting down: nobody is left to read the message.
        }
    }

    private void Report(Exception error) => _dialogs.ShowMessage("Error", error.Message);

    private void OnVmChanged(object? sender, PropertyChangedEventArgs e) => RequestRefresh();

    /// <summary>
    /// One refresh per burst of changes, a few milliseconds later (at most about 25 a second): <c>Invoke</c> on the UI thread would run the refresh
    /// at once, in the middle of the view model applying the burst, once per row.
    /// </summary>
    private void RequestRefresh()
    {
        if (_refreshPending || _disposed) return;
        _refreshPending = true;
        try
        {
            _app.AddTimeout(TimeSpan.FromMilliseconds(40), () =>
            {
                RefreshAll();
                return false;
            });
        }
        catch (Exception)
        {
            // The application is shutting down.
            _refreshPending = false;
        }
    }

    // ---------------------------------------------------------------- input

    private void Fire(int command)
    {
        if (!Allowed(command)) return;
        var commands = new[] { _vm.StartCommand, _vm.DryRunCommand, _vm.ScanCommand, _vm.CancelCommand, _vm.RetryFailedCommand };
        commands[command].Fire(Report);
    }

    /// <summary>Page keys, routed here by the shell whatever has the focus. True when the key was used.</summary>
    public bool HandleKey(Key key)
    {
        if (key == Key.R) Fire(0);
        else if (key == Key.D) Fire(1);
        else if (key == Key.S) Fire(2);
        else if (key == Key.X) Fire(3);
        else if (key == Key.T) Fire(4);
        else if (key == Key.L) ToggleLog();
        else if (key == Key.D1) Toggle(FileFilter.Succeeded);
        else if (key == Key.D2) Toggle(FileFilter.Failed);
        else if (key == Key.D3) Toggle(FileFilter.Skipped);
        else if (key == Key.D4) Toggle(FileFilter.Pending);
        else if (key == Key.End)
        {
            _vm.IsFollowing = true;
            RefreshAll();
        }
        else return false;
        return true;
    }

    private void Toggle(FileFilter flag)
    {
        _vm.Filter ^= flag;
        RefreshAll();
    }

    private void ToggleSource()
    {
        if (_sources.SelectedItem is not { } i || i < 0 || i >= _vm.Sources.Count) return;
        _vm.Sources[i].Included = !_vm.Sources[i].Included;
        RefreshAll();
    }

    public void ToggleLog()
    {
        if (_logList is null) return;
        _showLog = !_showLog;
        _logFrame.Visible = _showLog;
        _table.Height = Dim.Fill(_showLog ? LogRows : 0);
        RefreshAll();
        FocusDefault();
    }

    // ---------------------------------------------------------------- layout

    private void Build()
    {
        var sources = new FrameView { Title = "Sources", BorderStyle = LineStyle.Single, X = 0, Y = 0, Width = LeftWidth, Height = 5, CanFocus = true };
        _sources.X = 0;
        _sources.Y = 0;
        _sources.Width = Dim.Fill();
        _sources.Height = Dim.Fill();
        sources.Add(_sources);

        var files = new FrameView { Title = "Files", BorderStyle = LineStyle.Single, X = 0, Y = 5, Width = LeftWidth, Height = 6, CanFocus = true };
        for (var i = 0; i < 4; i++)
        {
            _filters[i].X = 0;
            _filters[i].Y = i;
            files.Add(_filters[i]);
        }

        var run = new FrameView { Title = "Run", BorderStyle = LineStyle.Single, X = 0, Y = 11, Width = LeftWidth, Height = 7, CanFocus = true };
        for (var i = 0; i < 5; i++)
        {
            _buttons[i].X = 0;
            _buttons[i].Y = i;
            run.Add(_buttons[i]);
        }

        sources.SetScheme(Theme.Pane);
        files.SetScheme(Theme.Pane);
        run.SetScheme(Theme.Pane);

        _summary.X = LeftWidth + 1;
        _summary.Y = 0;
        _summary.Width = Dim.Fill();
        _summary.Height = 1;
        _bar.X = LeftWidth + 1;
        _bar.Y = 1;
        _bar.Width = Dim.Fill();
        _bar.Height = 1;
        _banner.X = LeftWidth + 1;
        _banner.Y = Pos.Bottom(_bar);
        _banner.Width = Dim.Fill();
        _table.X = LeftWidth + 1;
        _table.Y = Pos.Bottom(_banner);
        _table.Width = Dim.Fill();
        _table.Height = Dim.Fill();
        _logFrame.X = LeftWidth + 1;
        _logFrame.Y = Pos.AnchorEnd(LogRows);
        _logFrame.Width = Dim.Fill();
        _logFrame.Height = LogRows;
        _logFrame.SetScheme(Theme.Pane);

        Add(sources, files, run, _summary, _bar, _banner, _table, _logFrame);
    }

    protected override void Dispose(bool disposing)
    {
        if (disposing)
        {
            _disposed = true;
            _vm.PropertyChanged -= OnVmChanged;
        }

        base.Dispose(disposing);
    }
}

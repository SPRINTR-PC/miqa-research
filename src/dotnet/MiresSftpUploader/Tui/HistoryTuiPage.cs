using System;
using System.Collections.Generic;
using System.Linq;
using System.Reactive.Linq;
using MiresSftpUploader.Core;
using MiresSftpUploader.SettingsTui;
using MiresSftpUploader.ViewModels;
using Terminal.Gui.Drawing;
using Terminal.Gui.Input;
using Terminal.Gui.ViewBase;
using Terminal.Gui.Views;

namespace MiresSftpUploader.Tui;

/// <summary>The Run list as a table over the live <see cref="HistoryPageViewModel.Runs"/> (symbol, started, status); rows are never copied.</summary>
public sealed class RunListSource(IReadOnlyList<RunItemViewModel> runs) : ITableSource
{
    public string[] ColumnNames { get; } = ["", "Started", "Status"];
    public int Columns => 3;
    public int Rows => runs.Count;

    public object this[int row, int col]
    {
        get
        {
            if (row < 0 || row >= runs.Count) return "";
            var r = runs[row];
            return col switch { 0 => OutcomeSymbols.OfRun(r.StatusText), 1 => r.StartedText[5..], _ => r.StatusText };
        }
    }
}

/// <summary>The outcomes of the selected Run, read live from <see cref="RunItemViewModel.VisibleFiles"/> through a getter.</summary>
public sealed class RunOutcomesSource(Func<IReadOnlyList<HistoryFileRow>> rows) : ITableSource
{
    public string[] ColumnNames { get; } = ["", "Source", "File", "Status"];
    public int Columns => 4;
    public int Rows => rows().Count;

    public object this[int row, int col]
    {
        get
        {
            var list = rows();
            if (row < 0 || row >= list.Count) return "";
            var r = list[row];
            return col switch { 0 => OutcomeSymbols.OfRecorded(r.Outcome), 1 => r.Source, 2 => r.Path, _ => r.ReasonText.Length > 0 ? r.ReasonText : r.OutcomeText };
        }
    }
}

/// <summary>
/// The History page ("Split" layout) on the real <see cref="HistoryPageViewModel"/>: a 34-column Run list with the filters All / Attention / Live,
/// the selected Run beside it. Keys (routed by the shell): 1-3 filter, F Failed only, R Retry, X Cancel, J/C export, F5 refresh.
/// Updates from live Runs arrive in bursts: they set a flag and one posted flush redraws.
/// </summary>
public sealed class HistoryTuiPage : View, IShellPage
{
    private static readonly string[] FilterNames = ["All", "Attention", "Live"];
    private static readonly System.Text.Rune NoHotKey = new('￿');

    private readonly HistoryPageViewModel _vm;
    private readonly Action<Action> _post;
    private readonly TableView _runs = new() { FullRowSelect = true, MultiSelect = false };
    private readonly TableView _files = new() { FullRowSelect = true, MultiSelect = false };
    private readonly FrameView _listFrame = new() { Title = "Runs", BorderStyle = LineStyle.Single };
    private readonly FrameView _detailFrame = new() { Title = "Run", BorderStyle = LineStyle.Single };
    private readonly Button[] _filterButtons = [new(), new(), new()];
    private readonly Button[] _actions = [new(), new(), new(), new()];
    private readonly Label _head = new();
    private readonly Label _banner = new();
    private readonly Label _counts = new();
    private readonly Label _notice = new();
    private readonly Label _outcomes = new();
    private readonly ProgressBar _bar = new() { ProgressBarFormat = ProgressBarFormat.SimplePlusPercentage };
    private readonly CheckBox _failedOnly = new() { Text = "Failed only" };

    // Failed only per Run: kept here because a refresh makes new RunItemViewModels. Absent = not decided yet (default: on when the Run needs attention).
    private readonly Dictionary<Guid, bool> _failedOnlyChoice = [];
    private bool _refreshPending;
    private bool _syncing;
    private RunItemViewModel? _watched;

    /// <param name="post">Runs an action on the UI thread (<c>app.Invoke</c>).</param>
    public HistoryTuiPage(HistoryPageViewModel vm, Action<Action> post)
    {
        _vm = vm;
        _post = post;
        CanFocus = true;

        _runs.Table = new RunListSource(vm.Runs);
        _files.Table = new RunOutcomesSource(() => (IReadOnlyList<HistoryFileRow>?)vm.Selected?.VisibleFiles ?? []);
        foreach (var t in new[] { _runs, _files })
        {
            t.Style.AlwaysShowHeaders = true;
            t.Style.ShowHorizontalHeaderOverline = false;
            t.Style.ExpandLastColumn = true;
            t.Style.ColumnStyles[0] = new ColumnStyle { MinWidth = 1, MaxWidth = 1 };
            t.SetScheme(Theme.Pane);
        }

        _files.Style.ColumnStyles[1] = new ColumnStyle { MinWidth = 6, MaxWidth = 14 };
        _files.Style.ColumnStyles[2] = new ColumnStyle { MinWidth = 12, MaxWidth = 28 };
        _runs.ValueChanged += (_, e) =>
        {
            var row = e.NewValue?.SelectedCell.Y ?? -1;
            if (_syncing || row < 0 || row >= vm.Runs.Count || ReferenceEquals(vm.Selected, vm.Runs[row])) return;
            vm.Selected = vm.Runs[row];
            RefreshAll();
        };

        for (var i = 0; i < 3; i++)
        {
            var kind = (RunFilterKind)i;
            _filterButtons[i] = new Button { NoPadding = true, ShadowStyle = ShadowStyles.None };
            _filterButtons[i].Accepting += (_, e) => { SetFilter(kind); e.Handled = true; };
        }

        var labels = new[] { "Cancel", "Retry", "JSON", "CSV" };
        for (var i = 0; i < 4; i++)
        {
            var n = i;
            _actions[i] = new Button { Text = labels[i], NoPadding = true, ShadowStyle = ShadowStyles.None };
            _actions[i].Accepting += (_, e) => { Act(n); e.Handled = true; };
        }

        // A CheckBox click flips its own value and never raises Accepting: bind through ValueChanged and compare with the state.
        _failedOnly.ValueChanged += (_, _) =>
        {
            if (_syncing || _vm.Selected is not { } r || r.FailedOnly == (_failedOnly.Value == CheckState.Checked)) return;
            SetFailedOnly(r, !r.FailedOnly);
            RefreshAll();
        };

        _bar.SetScheme(Theme.Ok);
        _banner.SetScheme(Theme.Locked);
        _notice.SetScheme(Theme.Help);
        _listFrame.SetScheme(Theme.Pane);
        _detailFrame.SetScheme(Theme.Pane);
        foreach (var l in new[] { _head, _banner, _counts, _notice, _outcomes }) l.HotKeySpecifier = NoHotKey;

        vm.PropertyChanged += (_, _) => RequestRefresh();
        vm.Runs.CollectionChanged += (_, _) => RequestRefresh();
        Build();
        RefreshAll();
    }

    public HistoryPageViewModel Vm => _vm;

    public string StatusText
    {
        get
        {
            var live = _vm.Runs.Count(r => r.IsLive);
            var attention = _vm.Runs.Count(r => r.NeedsAttention);
            return $"{_vm.Runs.Count} Runs, {live} live, {attention} need attention";
        }
    }

    public string KeyHints => "1-3 Filter  F Failed  R Retry  X Cancel  J/C Export";

    public void FocusDefault()
    {
        if (!IsInitialized || !Visible) return;
        _runs.SetFocus();
    }

    public bool HandleKey(Key key)
    {
        var k = key.NoShift;
        if (k == Key.D1) SetFilter(RunFilterKind.All);
        else if (k == Key.D2) SetFilter(RunFilterKind.NeedsAttention);
        else if (k == Key.D3) SetFilter(RunFilterKind.Live);
        else if (k == Key.F5) { _vm.Refresh(); RefreshAll(); }
        else if (k == Key.R) Act(1);
        else if (k == Key.X) Act(0);
        else if (k == Key.J) Act(2);
        else if (k == Key.C) Act(3);
        else if (k == Key.F)
        {
            if (_vm.Selected is { } r) SetFailedOnly(r, !r.FailedOnly);
            RefreshAll();
        }
        else return false;
        return true;
    }

    private void SetFilter(RunFilterKind kind)
    {
        _vm.Filter = kind;
        RefreshAll();
    }

    private void SetFailedOnly(RunItemViewModel r, bool on)
    {
        _failedOnlyChoice[r.RunId] = on;
        r.FailedOnly = on;
    }

    private void Fail(Exception e) => MessageBox.ErrorQuery(App!, "Error", e.Message, "_Ok");

    private void Act(int i)
    {
        if (_vm.Selected is not { } r) return;
        var cmd = i switch { 0 => r.CancelCommand, 1 => r.RetryCommand, 2 => r.ExportJsonCommand, _ => r.ExportCsvCommand };
        cmd.CanExecute.Take(1).Subscribe(can => { if (can) cmd.Execute().Subscribe(_ => { }, Fail); });
        RefreshAll();
    }

    private void RequestRefresh()
    {
        if (_refreshPending) return;
        _refreshPending = true;
        _post(RefreshAll);
    }

    public void RefreshAll()
    {
        _refreshPending = false;
        _syncing = true;
        for (var i = 0; i < 3; i++) _filterButtons[i].Text = (i == _vm.FilterIndex ? "●" : "○") + FilterNames[i];
        if (_vm.Selected is null && _vm.Runs.Count > 0) _vm.Selected = _vm.Runs[0];
        ApplyFailedOnlyDefault();
        _runs.Update();
        if (_vm.Selected is { } sel)
        {
            var row = _vm.Runs.IndexOf(sel);
            if (row >= 0 && (_runs.Value?.SelectedCell.Y ?? -1) != row)
            {
                _runs.SetSelection(0, row, false);
                _runs.EnsureCursorIsVisible();
            }
        }

        if (_vm.Selected is not { } r)
        {
            _head.Text = _vm.IsEmpty ? "No Runs." : "";
            _banner.Text = _counts.Text = _outcomes.Text = "";
            _bar.Fraction = 0;
            foreach (var a in _actions) a.Enabled = false;
        }
        else
        {
            if (!ReferenceEquals(_watched, r))
            {
                _watched = r;
                r.PropertyChanged += (_, _) => { if (ReferenceEquals(_watched, r)) RequestRefresh(); };
            }

            _head.Text = $"{r.Title}  {OutcomeSymbols.OfRun(r.StatusText)} {r.StatusText}  {r.ExitText}\n{r.Who} · {r.ModeText} · {r.StartedText[5..]} · {r.DurationText}";
            _banner.Text = r.IsLiveOthers && r.ShowCancelRequested ? $"Live view of {r.StartedBy}'s Run (read-only). Cancel requested: it stops at its next cancel poll."
                : r.IsLiveOthers ? $"Live view of {r.StartedBy}'s Run: read-only, you can watch it or ask it to stop. Heartbeat {r.HeartbeatText}."
                : r.ShowCancelRequested ? "Cancel requested. The Run stops at its next cancel poll; in-flight .part files stay on the server."
                : r.IsAbandoned ? "Abandoned: the process stopped without finishing. Unfinished files are marked Failed; Retry starts them now."
                : r.IsDryRun ? "Dry Run: nothing was uploaded, archived or recorded."
                : "";
            _bar.Fraction = (float)(r.Progress / 100.0);
            _counts.Text = $"✓ {r.Succeeded}  ✗ {r.Failed}  ⊘ {r.Skipped} ({r.TooRecent} Too Recent)  → {r.MovedAway}";
            _outcomes.Text = $"Outcomes ({r.VisibleFiles.Count})";
            _failedOnly.Value = r.FailedOnly ? CheckState.Checked : CheckState.UnChecked;
            _actions[0].Text = r.IsOwn ? "Cancel" : "Request cancel";
            _actions[0].Enabled = r.IsLive && !r.CancelRequested;
            _actions[1].Enabled = !r.IsLive && (r.Failed > 0 || r.IsAbandoned);
            _actions[2].Enabled = _actions[3].Enabled = true;
        }

        _notice.Text = Fit(_vm.Notice, Math.Max(_notice.Frame.Width, 20));
        _files.Update();
        _syncing = false;
        SetNeedsDraw();
    }

    // One line: a path too long for it loses its beginning, not its file name.
    private static string Fit(string text, int width) => text.Length <= width ? text : "…" + text[^(width - 1)..];

    // A Run that needs attention opens with Failed only on; a later choice of the user (also across refreshes) stands.
    private void ApplyFailedOnlyDefault()
    {
        if (_vm.Selected is not { } r) return;
        if (!_failedOnlyChoice.TryGetValue(r.RunId, out var on))
        {
            on = r.NeedsAttention;
            _failedOnlyChoice[r.RunId] = on;
        }

        if (r.FailedOnly != on) r.FailedOnly = on;
    }

    private void Build()
    {
        _listFrame.X = 0; _listFrame.Y = 0; _listFrame.Width = 34; _listFrame.Height = Dim.Fill();
        _detailFrame.X = 34; _detailFrame.Y = 0; _detailFrame.Width = Dim.Fill(); _detailFrame.Height = Dim.Fill();

        Pos x = 0;
        foreach (var b in _filterButtons)
        {
            b.X = x; b.Y = 0;
            _listFrame.Add(b);
            x = Pos.Right(b) + 1;
        }

        _runs.X = 0; _runs.Y = 1; _runs.Width = Dim.Fill(); _runs.Height = Dim.Fill();
        _listFrame.Add(_runs);

        _head.X = 0; _head.Y = 0; _head.Width = Dim.Fill(); _head.Height = 2;
        _banner.X = 0; _banner.Y = 2; _banner.Width = Dim.Fill(); _banner.Height = 2;
        _bar.X = 0; _bar.Y = 4; _bar.Width = Dim.Fill(); _bar.Height = 1;
        _counts.X = 0; _counts.Y = 5; _counts.Width = Dim.Fill(); _counts.Height = 1;
        Pos ax = 0;
        foreach (var b in _actions)
        {
            b.X = ax; b.Y = 6;
            _detailFrame.Add(b);
            ax = Pos.Right(b) + 1;
        }

        _outcomes.X = 0; _outcomes.Y = 7; _outcomes.Width = 20; _outcomes.Height = 1;
        _failedOnly.X = Pos.AnchorEnd(14); _failedOnly.Y = 7;
        _files.X = 0; _files.Y = 8; _files.Width = Dim.Fill(); _files.Height = Dim.Fill(1);
        _notice.X = 0; _notice.Y = Pos.AnchorEnd(1); _notice.Width = Dim.Fill(); _notice.Height = 1;
        _detailFrame.Add(_head, _banner, _bar, _counts, _outcomes, _failedOnly, _files, _notice);

        Add(_listFrame, _detailFrame);
    }
}

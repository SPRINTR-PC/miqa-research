// PROTOTYPE (throwaway): fake Run History + Run controls for the History view question in the Wayfinder map.
// In-memory only. "Other users" are simulated; nothing touches the Upload State, SFTP or disk.
using System;
using System.Collections.ObjectModel;
using System.Linq;
using Avalonia.Threading;
using ReactiveUI;

namespace MiresSftpUploader.Prototype;

public class RunVm : ReactiveObject
{
    readonly ProtoVm _host;
    string _status;
    double _progress;
    bool _cancelRequested, _failedOnly;
    int _cancelTicks;
    string _heartbeat;
    int? _exit;

    public RunVm(ProtoVm host, int id, string started, string day, bool showDay, string by, string machine, string mode, string status, int? exit, string duration, string heartbeat = "")
    {
        _host = host; Id = id; Started = started; Day = day; ShowDay = showDay; StartedBy = by; Machine = machine; Mode = mode; _status = status; _exit = exit; Duration = duration; _heartbeat = heartbeat;
        SelectCmd = ReactiveCommand.Create(() => { _host.SelectedRun = this; });
        RetryCmd = ReactiveCommand.Create(() => _host.RetryFailed(this));
        CancelCmd = ReactiveCommand.Create(() => { CancelRequested = true; _cancelTicks = 0; _host.Say(IsMine ? $"Cancelling Run {Id}…" : $"Cancel requested for {StartedBy}'s Run {Id}: it stops at its next cancel poll (≤5 s)"); Notify(); });
        ExportJsonCmd = ReactiveCommand.Create(() => _host.Say($"Report written: ~/Documents/MIRES/reports/run-{Id:0000}.json ({Files.Count} files)"));
        ExportCsvCmd = ReactiveCommand.Create(() => _host.Say($"Report written: ~/Documents/MIRES/reports/run-{Id:0000}.csv ({Files.Count} files)"));
    }

    public int Id { get; }
    public string Title => $"Run {Id}";
    public string Started { get; }
    public string Day { get; }
    public bool ShowDay { get; }
    public string StartedBy { get; }
    public string Machine { get; }
    public string Mode { get; }
    public string Duration { get; set; }
    public bool IsMine => StartedBy == "josef";
    public bool IsOthers => !IsMine;
    public string Who => IsMine ? "you" : StartedBy;
    public string Where => $"{StartedBy} · {Machine}";
    public ObservableCollection<FileRow> Files { get; } = new();
    public ObservableCollection<FileRow> VisibleFiles { get; } = new();

    public ReactiveCommand<System.Reactive.Unit, System.Reactive.Unit> SelectCmd { get; }
    public ReactiveCommand<System.Reactive.Unit, System.Reactive.Unit> RetryCmd { get; }
    public ReactiveCommand<System.Reactive.Unit, System.Reactive.Unit> CancelCmd { get; }
    public ReactiveCommand<System.Reactive.Unit, System.Reactive.Unit> ExportJsonCmd { get; }
    public ReactiveCommand<System.Reactive.Unit, System.Reactive.Unit> ExportCsvCmd { get; }

    public string Status { get => _status; set { this.RaiseAndSetIfChanged(ref _status, value); Notify(); } }
    public int? Exit { get => _exit; set { this.RaiseAndSetIfChanged(ref _exit, value); Notify(); } }
    public double Progress { get => _progress; set { this.RaiseAndSetIfChanged(ref _progress, value); } }
    public bool CancelRequested { get => _cancelRequested; set { this.RaiseAndSetIfChanged(ref _cancelRequested, value); Notify(); } }
    public bool FailedOnly { get => _failedOnly; set { this.RaiseAndSetIfChanged(ref _failedOnly, value); RefreshFiles(); } }
    public string Heartbeat { get => _heartbeat; set => this.RaiseAndSetIfChanged(ref _heartbeat, value); }
    public int CancelTicks { get => _cancelTicks; set => _cancelTicks = value; }

    public bool IsRunning => Status == "Running";
    public bool IsAbandoned => Status == "Abandoned";
    public bool IsLiveOthers => IsRunning && IsOthers;
    public bool IsLiveMine => IsRunning && IsMine;
    public bool HasFailures => Files.Any(f => f.IsFail);
    public bool CanRetry => HasFailures && !IsRunning;
    public bool CanCancel => IsRunning && !CancelRequested;
    public bool ShowCancelRequested => IsRunning && CancelRequested;
    public string CancelLabel => IsMine ? "■ Cancel" : $"■ Request cancel ({StartedBy}'s Run)";
    public bool DotOk => Status == "Succeeded";
    public bool DotFail => Status == "Finished with failures";
    public bool DotActive => IsRunning;
    public bool DotWarn => Status is "Abandoned" or "Cancelled";
    public string ExitText => Exit is { } e ? $"exit code {e}" : "no exit code";
    public string Subtitle => $"{Started} · {Where} · {Mode} · {Duration}";
    public string Line2 => $"{Who} · {Mode}";
    public int Ok => Files.Count(f => f.IsOk);
    public int Failed => Files.Count(f => f.IsFail);
    public int Moved => Files.Count(f => f.Note.StartsWith("moved"));
    public int TooRecent => Files.Count(f => f.Note.StartsWith("too recent"));
    public int Skipped => Files.Count(f => f.Outcome == "Skipped");
    public int Total => Files.Count(f => f.Outcome != "Ignored");
    public string Counts => $"{Ok} ✓  {Failed} ✗  {Skipped} skipped";
    public string ProgressText => $"{Files.Count(f => f.IsOk || f.IsFail)} of {Total} files";
    public string DryNote => Mode == "Dry run" ? "Dry run: plan only, nothing was uploaded, archived, moved or recorded." : "";
    public bool IsDry => Mode == "Dry run";

    public void Notify()
    {
        foreach (var n in new[] { nameof(IsRunning), nameof(IsAbandoned), nameof(IsLiveOthers), nameof(IsLiveMine), nameof(HasFailures), nameof(CanRetry), nameof(CanCancel),
                     nameof(ShowCancelRequested), nameof(DotOk), nameof(DotFail), nameof(DotActive), nameof(DotWarn), nameof(ExitText), nameof(Ok), nameof(Failed),
                     nameof(Moved), nameof(TooRecent), nameof(Skipped), nameof(Total), nameof(Counts), nameof(ProgressText), nameof(Status) })
            this.RaisePropertyChanged(n);
    }

    public void RefreshFiles() { VisibleFiles.Clear(); foreach (var f in Files.Where(f => !_failedOnly || f.IsFail)) VisibleFiles.Add(f); }

    public void ApplyProgress()
    {
        var work = Files.Where(f => f.Outcome != "Ignored" && f.Outcome != "Skipped").ToList();
        var done = work.Count * Progress / 100.0;
        for (var i = 0; i < work.Count; i++)
        {
            if (i < Math.Floor(done)) { work[i].Outcome = "Succeeded"; work[i].Progress = 100; }
            else if (i == (int)Math.Floor(done)) { work[i].Outcome = "Uploading"; work[i].Progress = (done - Math.Floor(done)) * 100; }
            else { work[i].Outcome = "Pending"; work[i].Progress = 0; }
        }
        Notify();
    }
}

public partial class ProtoVm
{
    readonly DispatcherTimer _liveTimer = new() { Interval = TimeSpan.FromMilliseconds(700) };
    int _page, _runFilter;
    RunVm? _selectedRun;
    string _toast = "";
    public ObservableCollection<RunVm> Runs { get; } = new();
    public ObservableCollection<RunVm> VisibleRuns { get; } = new();
    public ObservableCollection<RunVm> LiveRuns { get; } = new();
    public ReactiveCommand<System.Reactive.Unit, System.Reactive.Unit> UploadPageCmd { get; private set; } = null!;
    public ReactiveCommand<System.Reactive.Unit, System.Reactive.Unit> HistoryPageCmd { get; private set; } = null!;
    public ReactiveCommand<System.Reactive.Unit, System.Reactive.Unit> BackToListCmd { get; private set; } = null!;

    public int Page { get => _page; set { this.RaiseAndSetIfChanged(ref _page, value); this.RaisePropertyChanged(nameof(IsHistoryPage)); } }
    public bool IsHistoryPage => Page == 1;
    public string[] RunFilters { get; } = ["All runs", "Needs attention", "Live now"];
    public int RunFilter { get => _runFilter; set { this.RaiseAndSetIfChanged(ref _runFilter, value); RefreshRuns(); } }
    public RunVm? SelectedRun
    {
        get => _selectedRun;
        set { this.RaiseAndSetIfChanged(ref _selectedRun, value); this.RaisePropertyChanged(nameof(HasSelection)); this.RaisePropertyChanged(nameof(NoSelection)); }
    }
    public bool HasSelection => SelectedRun != null;
    public bool NoSelection => SelectedRun == null;
    public string Toast { get => _toast; set { this.RaiseAndSetIfChanged(ref _toast, value); this.RaisePropertyChanged(nameof(HasToast)); } }
    public bool HasToast => Toast.Length > 0;
    public bool HasLive => LiveRuns.Count > 0;

    public void Say(string t) { Toast = t; }

    void InitHistory()
    {
        UploadPageCmd = ReactiveCommand.Create(() => { Page = 0; });
        HistoryPageCmd = ReactiveCommand.Create(() => { Page = 1; });
        BackToListCmd = ReactiveCommand.Create(() => { SelectedRun = null; });

        RunVm Make(int id, string at, string day, bool showDay, string by, string machine, string mode, string status, int? exit, string dur, string hb, (string src, string path, string size, string outcome, string note)[] files)
        {
            var r = new RunVm(this, id, at, day, showDay, by, machine, mode, status, exit, dur, hb);
            foreach (var f in files)
                r.Files.Add(new FileRow { Source = f.src, Path = f.path, Size = f.size, Outcome = f.outcome, Note = f.note });
            r.RefreshFiles(); return r;
        }
        (string, string, string, string, string) F(string p, string size, string o = "Succeeded", string note = "") => ("wsi-archive", p, size, o, note);

        var live = Make(42, "12:41", "Today", true, "sofia", "LAB-PC-07", "Headless", "Running", null, "12 min", "2 s ago",
            [F("case-050/slide-01.ndpi", "4.4 GB"), F("case-050/slide-02.ndpi", "3.9 GB"), F("case-051/slide-01.ndpi", "5.2 GB"), F("case-051/slide-02.ndpi", "2.7 GB"),
             F("case-052/slide-01.ndpi", "6.1 GB"), F("case-052/notes.txt", "3 KB"), F("case-053/slide-01.ndpi", "4.0 GB"), F("case-053/Thumbs.db", "12 KB", "Ignored", "pattern: (^|/)Thumbs\\.db$"),
             F("case-054/slide-01.ndpi", "5.5 GB"), F("case-054/slide-02.ndpi", "5.0 GB"), F("case-040/slide-01.ndpi", "4.1 GB", "Skipped", "unchanged since last upload")]);
        live.Progress = 38; live.ApplyProgress();

        var fail = Make(41, "09:15", "Today", false, "josef", "WS-JOSEF", "UI", "Finished with failures", 1, "1 h 02 min", "",
            [F("case-041/slide-01.ndpi", "4.2 GB", note: "moved to /data/done/case-041/slide-01.ndpi"), F("case-041/slide-02.ndpi", "3.8 GB", note: "moved to /data/done/case-041/slide-02.ndpi"),
             F("case-042/slide-01.ndpi", "5.1 GB", "Failed", "Connection reset by peer (3/3 attempts) · moved to /data/failed/case-042/slide-01.ndpi"),
             F("case-042/notes.txt", "2 KB", note: "moved to /data/done/case-042/notes.txt"), F("case-043/slide-01.ndpi", "2.9 GB", note: "moved to /data/done/case-043/slide-01.ndpi"),
             F("case-043/Thumbs.db", "12 KB", "Ignored", "pattern: (^|/)Thumbs\\.db$"), F("case-044/slide-01.ndpi", "6.4 GB", "Skipped", "unchanged since last upload"),
             F("case-045/slide-01.ndpi", "4.8 GB", "Skipped", "too recent: modified 14 s ago (minimum age 60 s)"),
             F("case-045/slide-02.ndpi", "4.6 GB", "Failed", "RemoteDenied: server refused rename over existing file"),
             F("dicom/series-007.zip", "1.1 GB", note: "archive · 1,204 members · moved")]);

        var ok = Make(40, "06:00", "Today", false, "svc-uploader", "LAB-PC-07", "Headless", "Succeeded", 0, "23 min", "",
            [F("case-038/slide-01.ndpi", "4.0 GB"), F("case-038/slide-02.ndpi", "4.1 GB"), F("case-039/slide-01.ndpi", "5.0 GB"), F("case-039/report.pdf", "640 KB"),
             F("case-037/slide-01.ndpi", "3.3 GB", "Skipped", "unchanged since last upload")]);

        var aband = Make(39, "23:00", "Yesterday", true, "svc-uploader", "LAB-PC-07", "Headless", "Abandoned", null, "stopped after 8 min", "",
            [F("case-030/slide-01.ndpi", "4.4 GB"), F("case-030/slide-02.ndpi", "3.1 GB"), F("case-031/slide-01.ndpi", "5.9 GB", "Failed", "Run abandoned while uploading: .part left on server, retried by the next Run"),
             F("case-031/slide-02.ndpi", "2.2 GB", "Pending", "never started")]);

        var dry = Make(38, "16:20", "Yesterday", false, "josef", "WS-JOSEF", "Dry run", "Succeeded", 0, "6 s", "",
            [F("case-030/slide-01.ndpi", "4.4 GB", "Pending", "would upload"), F("case-030/slide-02.ndpi", "3.1 GB", "Pending", "would upload"), F("case-031/slide-01.ndpi", "5.9 GB", "Pending", "would upload"),
             F("case-031/Thumbs.db", "12 KB", "Ignored", "pattern: (^|/)Thumbs\\.db$")]);

        var cancelled = Make(37, "11:05", "Yesterday", false, "sofia", "LAB-PC-07", "UI", "Cancelled", 130, "4 min", "",
            [F("case-020/slide-01.ndpi", "4.4 GB"), F("case-020/slide-02.ndpi", "3.1 GB", "Failed", "Cancelled by josef (cross-user cancel) while uploading"), F("case-020/slide-03.ndpi", "2.5 GB", "Pending", "not started")]);

        var older = Make(36, "06:00", "Earlier", true, "svc-uploader", "LAB-PC-07", "Headless", "Succeeded", 0, "31 min", "",
            [F("case-010/slide-01.ndpi", "4.0 GB"), F("case-010/slide-02.ndpi", "4.2 GB"), F("case-011/slide-01.ndpi", "5.4 GB"), F("dicom/series-006.zip", "980 MB", note: "archive · 880 members")]);

        foreach (var r in new[] { live, fail, ok, aband, dry, cancelled, older }) Runs.Add(r);
        RefreshRuns();
        SelectedRun = fail;
        _liveTimer.Tick += (_, _) => LiveTick();
        _liveTimer.Start();
    }

    public void RefreshRuns()
    {
        VisibleRuns.Clear();
        foreach (var r in Runs.Where(r => RunFilter switch { 1 => r.HasFailures || r.IsAbandoned || r.Status == "Cancelled", 2 => r.IsRunning, _ => true }))
            VisibleRuns.Add(r);
        LiveRuns.Clear(); foreach (var r in Runs.Where(r => r.IsRunning)) LiveRuns.Add(r);
        this.RaisePropertyChanged(nameof(HasLive));
    }

    public void RetryFailed(RunVm from)
    {
        var failed = from.Files.Where(f => f.IsFail).ToList();
        var run = new RunVm(this, Runs.Max(r => r.Id) + 1, DateTime.Now.ToString("HH:mm"), "Today", false, "josef", "WS-JOSEF", "UI", "Running", null, "just now", "1 s ago");
        foreach (var f in failed) run.Files.Add(new FileRow { Source = f.Source, Path = f.Path, Size = f.Size, Note = $"retry of Run {from.Id}" });
        run.RefreshFiles(); run.ApplyProgress();
        Runs.Insert(0, run); RefreshRuns(); Say($"Run {run.Id} started: retrying {failed.Count} failed file(s) from Run {from.Id}");
        if (SelectedRun != null) SelectedRun = run;
    }

    void LiveTick()
    {
        var changed = false;
        foreach (var r in Runs.Where(r => r.IsRunning).ToList())
        {
            if (r.CancelRequested)
            {
                r.CancelTicks++;
                if (r.CancelTicks >= 4)
                {
                    r.Status = "Cancelled"; r.Exit = 130; r.CancelRequested = false; r.Heartbeat = "";
                    foreach (var f in r.Files.Where(f => f.IsActive)) { f.Outcome = "Failed"; f.Note = $"Cancelled by {(r.IsMine ? "you" : "josef (cross-user cancel)")} while uploading"; }
                    foreach (var f in r.Files.Where(f => f.Outcome == "Pending")) f.Note = "not started";
                    r.Notify(); changed = true; Say($"Run {r.Id} cancelled (exit code 130)");
                }
                continue;
            }
            r.Progress = Math.Min(100, r.Progress + (r.IsMine ? 9 : 1.6));
            r.Heartbeat = $"{1 + (int)(r.Progress * 7) % 4} s ago";
            if (r.Progress >= 100) { r.Status = r.HasFailures ? "Finished with failures" : "Succeeded"; r.Exit = r.HasFailures ? 1 : 0; r.Heartbeat = ""; r.Duration = "just now"; changed = true; Say($"Run {r.Id} finished"); }
            r.ApplyProgress(); r.RefreshFiles();
        }
        if (changed) RefreshRuns();
    }
}

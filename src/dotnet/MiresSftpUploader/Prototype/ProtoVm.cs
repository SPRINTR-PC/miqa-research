// PROTOTYPE (throwaway): fake data + simulated run for the UI layout question in the Wayfinder map.
// Everything here is in-memory; nothing touches SFTP, S3 or disk.
using System;
using System.Collections.ObjectModel;
using System.Linq;
using Avalonia;
using Avalonia.Styling;
using Avalonia.Threading;
using ReactiveUI;
using MiresSftpUploader.ViewModels;

namespace MiresSftpUploader.Prototype;

public class FileRow : ReactiveObject
{
    string _outcome = "Pending";
    double _progress;
    string _note = "";

    public string Path { get; init; } = "";
    public string Size { get; init; } = "";
    public bool IsArchive { get; init; }
    public string Source { get; init; } = "";

    public string Outcome
    {
        get => _outcome;
        set
        {
            this.RaiseAndSetIfChanged(ref _outcome, value);
            this.RaisePropertyChanged(nameof(IsOk));
            this.RaisePropertyChanged(nameof(IsFail));
            this.RaisePropertyChanged(nameof(IsActive));
            this.RaisePropertyChanged(nameof(IsMuted));
        }
    }
    public double Progress { get => _progress; set => this.RaiseAndSetIfChanged(ref _progress, value); }
    public string Note { get => _note; set => this.RaiseAndSetIfChanged(ref _note, value); }

    public bool IsOk => Outcome == "Succeeded";
    public bool IsFail => Outcome == "Failed";
    public bool IsActive => Outcome is "Hashing" or "Uploading";
    public bool IsMuted => Outcome is "Skipped" or "Ignored" or "Pending";
}

// PROTOTYPE: one configurable Source. Type decides which fields apply (Directory vs S3).
public class SourceVm : ReactiveObject
{
    string _name = "", _type = "Directory", _path = "", _endpoint = "", _bucket = "", _prefix = "", _region = "", _remotePath = "";
    bool _enabled = true, _pathStyle = true;
    readonly Action<SourceVm> _remove;
    public SourceVm(Action<SourceVm> remove) { _remove = remove; RemoveCmd = ReactiveCommand.Create(() => _remove(this)); }

    public string[] Types { get; } = ["Directory", "S3"];
    public ReactiveCommand<System.Reactive.Unit, System.Reactive.Unit> RemoveCmd { get; }
    public string Name { get => _name; set { this.RaiseAndSetIfChanged(ref _name, value); Touch(); } }
    public int TypeIndex
    {
        get => _type == "S3" ? 1 : 0;
        set { this.RaiseAndSetIfChanged(ref _type, value == 1 ? "S3" : "Directory"); this.RaisePropertyChanged(nameof(IsDirectory)); this.RaisePropertyChanged(nameof(IsS3)); Touch(); }
    }
    public bool IsDirectory => _type == "Directory";
    public bool IsS3 => _type == "S3";
    public string Path { get => _path; set { this.RaiseAndSetIfChanged(ref _path, value); Touch(); } }
    public string Endpoint { get => _endpoint; set => this.RaiseAndSetIfChanged(ref _endpoint, value); }
    public string Bucket { get => _bucket; set { this.RaiseAndSetIfChanged(ref _bucket, value); Touch(); } }
    public string Prefix { get => _prefix; set { this.RaiseAndSetIfChanged(ref _prefix, value); Touch(); } }
    public string Region { get => _region; set => this.RaiseAndSetIfChanged(ref _region, value); }
    public bool PathStyle { get => _pathStyle; set => this.RaiseAndSetIfChanged(ref _pathStyle, value); }
    public string RemotePath { get => _remotePath; set => this.RaiseAndSetIfChanged(ref _remotePath, value); }
    public string RemotePathHint => $"(default: /incoming/{(string.IsNullOrWhiteSpace(Name) ? "<name>" : Name)})";
    public bool Enabled { get => _enabled; set => this.RaiseAndSetIfChanged(ref _enabled, value); }
    public string Summary => IsS3 ? $"S3 · {Bucket}/{Prefix}" : $"Directory · {Path}";
    void Touch() { this.RaisePropertyChanged(nameof(Summary)); this.RaisePropertyChanged(nameof(RemotePathHint)); }
}

public record LogLine(int Level, string Time, string LevelName, string Text);

public partial class ProtoVm : ViewModelBase
{
    static readonly string[] Levels = ["Debug", "Information", "Warning", "Error"];
    readonly DispatcherTimer _timer = new() { Interval = TimeSpan.FromMilliseconds(140) };
    int _tick;
    bool _running, _finished, _failedOnly, _isDark = true, _showSettings, _dryRun, _fpConfirm;
    int _step, _logLevel = 1;

    public ObservableCollection<FileRow> Rows { get; } = new();
    public ObservableCollection<FileRow> VisibleRows { get; } = new();
    public ObservableCollection<LogLine> VisibleLogs { get; } = new();
    readonly System.Collections.Generic.List<LogLine> _logs = new();
    public string[] LevelNames => Levels;

    public ObservableCollection<SourceVm> Sources { get; } = new();
    public ReactiveCommand<System.Reactive.Unit, System.Reactive.Unit> AddSourceCmd { get; }
    public string Destination => "sftp.mires.example:22  →  /incoming/<source>/";

    public ReactiveCommand<System.Reactive.Unit, System.Reactive.Unit> ScanCmd { get; }
    public ReactiveCommand<System.Reactive.Unit, System.Reactive.Unit> DryRunCmd { get; }
    public ReactiveCommand<System.Reactive.Unit, System.Reactive.Unit> StartCmd { get; }
    public ReactiveCommand<System.Reactive.Unit, System.Reactive.Unit> CancelCmd { get; }
    public ReactiveCommand<System.Reactive.Unit, System.Reactive.Unit> RetryCmd { get; }
    public ReactiveCommand<System.Reactive.Unit, System.Reactive.Unit> ThemeCmd { get; }
    public ReactiveCommand<System.Reactive.Unit, System.Reactive.Unit> SettingsCmd { get; }
    public ReactiveCommand<System.Reactive.Unit, System.Reactive.Unit> FpCmd { get; }
    public ReactiveCommand<System.Reactive.Unit, System.Reactive.Unit> NextCmd { get; }
    public ReactiveCommand<System.Reactive.Unit, System.Reactive.Unit> BackCmd { get; }

    public ProtoVm()
    {
        Sources.Add(new SourceVm(r => Sources.Remove(r)) { Name = "wsi-archive", Path = "/data/wsi-archive" });
        Sources.Add(new SourceVm(r => Sources.Remove(r)) { Name = "dicom-export", TypeIndex = 1, Endpoint = "https://s3.mires.example", Bucket = "mires-bucket", Prefix = "export/", Region = "us-east-1" });
        AddSourceCmd = ReactiveCommand.Create(() => { Sources.Add(new SourceVm(r => Sources.Remove(r)) { Name = "new-source" }); });
        Seed();
        Log(1, "Configuration loaded (appsettings.json + appsettings.user.json + 2 environment overrides)");
        Log(1, "Scanned 2 Sources: 14 files, 3 ignored, 1 archive planned");
        _timer.Tick += (_, _) => Advance();
        ScanCmd = ReactiveCommand.Create(() => { Seed(); Log(1, "Scan complete: 14 files, 3 ignored"); Step = 1; });
        DryRunCmd = ReactiveCommand.Create(() => { _dryRun = true; Seed(); Log(1, "Dry run: 11 would upload, 1 archive (1,204 members), 3 ignored. Nothing written."); Step = 1; Raise(); });
        StartCmd = ReactiveCommand.Create(Start);
        CancelCmd = ReactiveCommand.Create(() => { _timer.Stop(); _running = false; Log(2, "Cancelled: in-flight files aborted, .part files left on server"); Raise(); });
        RetryCmd = ReactiveCommand.Create(() =>
        {
            foreach (var r in Rows.Where(r => r.IsFail)) { r.Outcome = "Pending"; r.Progress = 0; r.Note = ""; }
            _failedOnly = false; Start();
        });
        ThemeCmd = ReactiveCommand.Create(() =>
        {
            IsDark = !IsDark;
            if (Application.Current is { } app) app.RequestedThemeVariant = IsDark ? ThemeVariant.Dark : ThemeVariant.Light;
        });
        SettingsCmd = ReactiveCommand.Create(() => { ShowSettings = !ShowSettings; });
        FpCmd = ReactiveCommand.Create(() => { FpConfirm = !FpConfirm; });
        NextCmd = ReactiveCommand.Create(() => { Step = Math.Min(3, Step + 1); });
        BackCmd = ReactiveCommand.Create(() => { Step = Math.Max(0, Step - 1); });
        InitHistory();
    }

    public bool IsDark { get => _isDark; set { this.RaiseAndSetIfChanged(ref _isDark, value); this.RaisePropertyChanged(nameof(ThemeLabel)); } }
    public string ThemeLabel => IsDark ? "☀  Light" : "☾  Dark";
    public bool ShowSettings { get => _showSettings; set => this.RaiseAndSetIfChanged(ref _showSettings, value); }
    public bool FpConfirm { get => _fpConfirm; set => this.RaiseAndSetIfChanged(ref _fpConfirm, value); }
    public int Step
    {
        get => _step;
        set
        {
            this.RaiseAndSetIfChanged(ref _step, value);
            foreach (var n in new[] { nameof(IsStep0), nameof(IsStep1), nameof(IsStep2), nameof(IsStep3), nameof(Step0Done), nameof(Step1Done), nameof(Step2Done) })
                this.RaisePropertyChanged(n);
        }
    }
    public bool IsStep0 => Step == 0; public bool IsStep1 => Step == 1; public bool IsStep2 => Step == 2; public bool IsStep3 => Step == 3;
    public bool Step0Done => Step > 0; public bool Step1Done => Step > 1; public bool Step2Done => Step > 2;

    public bool IsRunning => _running;
    public bool IsIdle => !_running;
    public bool HasFailures => Rows.Any(r => r.IsFail);
    public bool FailedOnly
    {
        get => _failedOnly;
        set { this.RaiseAndSetIfChanged(ref _failedOnly, value); Refresh(); }
    }
    public int LogLevel
    {
        get => _logLevel;
        set { this.RaiseAndSetIfChanged(ref _logLevel, value); RefreshLogs(); }
    }

    public int Succeeded => Rows.Count(r => r.IsOk);
    public int Failed => Rows.Count(r => r.IsFail);
    public int Skipped => Rows.Count(r => r.Outcome == "Skipped");
    public int Ignored => Rows.Count(r => r.Outcome == "Ignored");
    public int Pending => Rows.Count(r => r.Outcome is "Pending" or "Hashing" or "Uploading");
    public double Overall
    {
        get
        {
            var work = Rows.Where(r => r.Outcome is not ("Ignored" or "Skipped")).ToList();
            return work.Count == 0 ? 0 : 100.0 * work.Count(r => r.Outcome is "Succeeded" or "Failed") / work.Count;
        }
    }
    public string Summary => $"{Succeeded} succeeded · {Failed} failed · {Skipped} skipped · {Ignored} ignored · {Pending} pending";
    public string StatusText => _running ? "Running…" : _finished ? (Failed > 0 ? "Finished with failures (exit code 1)" : "Finished (exit code 0)") : _dryRun ? "Dry run plan ready" : "Idle";

    void Raise()
    {
        foreach (var n in new[] { nameof(Succeeded), nameof(Failed), nameof(Skipped), nameof(Ignored), nameof(Pending), nameof(Overall), nameof(Summary),
                 nameof(StatusText), nameof(IsRunning), nameof(IsIdle), nameof(HasFailures) })
            this.RaisePropertyChanged(n);
    }

    void Seed()
    {
        Rows.Clear();
        void Add(string src, string p, string size, string outcome = "Pending", bool arc = false, string note = "") =>
            Rows.Add(new FileRow { Source = src, Path = p, Size = size, Outcome = outcome, IsArchive = arc, Note = note });
        Add("wsi-archive", "case-041/slide-01.ndpi", "4.2 GB");
        Add("wsi-archive", "case-041/slide-02.ndpi", "3.8 GB");
        Add("wsi-archive", "case-042/slide-01.ndpi", "5.1 GB");
        Add("wsi-archive", "case-042/notes.txt", "2 KB");
        Add("wsi-archive", "case-043/slide-01.ndpi", "2.9 GB");
        Add("wsi-archive", "case-043/Thumbs.db", "12 KB", "Ignored", note: "pattern: (^|/)Thumbs\\.db$");
        Add("wsi-archive", "case-044/slide-01.ndpi", "6.4 GB", "Skipped", note: "unchanged since last upload");
        Add("dicom-export", "series-007.zip", "1.1 GB", arc: true, note: "archive · 1,204 members");
        Add("dicom-export", "series-008.zip", "860 MB", arc: true, note: "archive · 902 members");
        Add("dicom-export", "report-2026-10.pdf", "640 KB");
        Add("dicom-export", "scratch/tmp-001.tmp", "8 KB", "Ignored", note: "pattern: \\.tmp$");
        Add("dicom-export", "scratch/tmp-002.tmp", "8 KB", "Ignored", note: "pattern: \\.tmp$");
        Add("dicom-export", "labels/label-018.png", "310 KB");
        Add("dicom-export", "labels/label-019.png", "295 KB");
        _finished = false; _running = false; _tick = 0; _logs.Clear();
        Refresh(); RefreshLogs(); Raise();
    }

    void Start()
    {
        if (_dryRun) { _dryRun = false; }
        foreach (var r in Rows.Where(r => r.Outcome == "Pending")) r.Progress = 0;
        _running = true; _finished = false; _timer.Start(); Step = 2;
        Log(1, "Run started: 11 files to upload, MaxParallelUploads=3");
        Log(0, "Connected to sftp.mires.example:22 (host key SHA256:2k9…q7Ew matches pinned fingerprint)");
        Raise();
    }

    void Advance()
    {
        _tick++;
        var active = Rows.Where(r => r.IsActive).ToList();
        foreach (var r in Rows.Where(r => r.Outcome == "Pending").Take(3 - active.Count)) { r.Outcome = "Hashing"; active.Add(r); Log(0, $"Hashing {r.Path}"); }
        foreach (var r in active)
        {
            r.Progress += r.Outcome == "Hashing" ? 25 : (r.IsArchive ? 14 : 9);
            if (r.Outcome == "Hashing" && r.Progress >= 100) { r.Outcome = "Uploading"; r.Progress = 0; Log(0, $"Uploading {r.Path}.part"); }
            else if (r.Outcome == "Uploading" && r.Path.StartsWith("case-042/slide") && r.Progress >= 55)
            {
                r.Outcome = "Failed"; r.Note = "Connection reset by peer (3/3 attempts)";
                Log(2, $"Retry 1/3 for {r.Path}: connection reset"); Log(2, $"Retry 2/3 for {r.Path}: connection reset");
                Log(3, $"Upload failed: {r.Path}: connection reset by peer"); if (FailedOnly) Refresh();
            }
            else if (r.Outcome == "Uploading" && r.Progress >= 100)
            {
                r.Outcome = "Succeeded"; r.Progress = 100; Log(1, $"Uploaded {r.Path} ({r.Size}) sha256 ok");
            }
        }
        if (Rows.All(r => !r.IsActive && r.Outcome != "Pending"))
        {
            _timer.Stop(); _running = false; _finished = true;
            Log(1, "Manifest uploaded: manifest.json, manifest.sha256");
            Log(Failed > 0 ? 3 : 1, $"Run finished: {Summary}");
            Step = 3;
        }
        Raise();
    }

    void Log(int level, string text)
    {
        var l = new LogLine(level, DateTime.Now.ToString("HH:mm:ss"), Levels[level].ToUpperInvariant()[..4], text);
        _logs.Add(l);
        if (level >= LogLevel) VisibleLogs.Add(l);
    }
    void RefreshLogs() { VisibleLogs.Clear(); foreach (var l in _logs.Where(l => l.Level >= LogLevel)) VisibleLogs.Add(l); }
    void Refresh() { VisibleRows.Clear(); foreach (var r in Rows.Where(r => !_failedOnly || r.IsFail)) VisibleRows.Add(r); }
}

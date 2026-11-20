using System;
using MiresSftpUploader.Core;
using ReactiveUI;

namespace MiresSftpUploader.ViewModels;

/// <summary>
/// The live progress of one file or Archive that is uploading now, from the latest <see cref="UploadProgress"/> snapshot. Nothing is
/// shown (<see cref="HasProgress"/> false) until the snapshot carries an Upload Speed, which Core only computes from 2 samples.
/// An Archive has no row in the file list, so these also stand alone in <see cref="UploadPageViewModel.ActiveUploads"/>.
/// </summary>
public sealed class UploadProgressViewModel(string source, string path, bool isArchive = false) : ViewModelBase
{
    private long _bytesSent;
    private long _total;
    private double? _speed;

    public string Source { get; } = source;
    public string Path { get; } = path;
    public TransferKey Key { get; } = new(source, path, isArchive);

    /// <summary>The last path segment, for a narrow card.</summary>
    public string Name { get; } = path[(path.LastIndexOfAny(['/', '\\']) + 1)..];

    /// <summary>Server-acknowledged bytes so far.</summary>
    public long BytesSent => _bytesSent;
    public long Total => _total;

    /// <summary>True once an Upload Speed is known: only then a bar, percent and speed are shown.</summary>
    public bool HasProgress => _speed is not null;

    /// <summary>0 to 1, clamped.</summary>
    public double Fraction => _total <= 0 ? 0 : Math.Clamp(_bytesSent / (double)_total, 0, 1);

    /// <summary>0 to 100, for a ProgressBar.</summary>
    public double Percent => Fraction * 100;

    /// <summary>Whole percent, rounded down: <c>42%</c> (100% only when everything is acknowledged).</summary>
    public string PercentText => $"{(int)Math.Floor(Percent)}%";

    /// <summary><c>3.1 MiB/s</c>; empty while <see cref="HasProgress"/> is false.</summary>
    public string SpeedText => _speed is { } s ? TransferFormat.Speed(s) : "";

    internal void Apply(UploadingFile file)
    {
        _bytesSent = file.BytesSent;
        _total = file.Total;
        _speed = file.UploadSpeed;
        RaiseAll();
    }

    internal void Clear()
    {
        if (_speed is null && _bytesSent == 0) return;
        _bytesSent = 0;
        _speed = null;
        RaiseAll();
    }

    private void RaiseAll()
    {
        this.RaisePropertyChanged(nameof(BytesSent));
        this.RaisePropertyChanged(nameof(Total));
        this.RaisePropertyChanged(nameof(HasProgress));
        this.RaisePropertyChanged(nameof(Fraction));
        this.RaisePropertyChanged(nameof(Percent));
        this.RaisePropertyChanged(nameof(PercentText));
        this.RaisePropertyChanged(nameof(SpeedText));
    }
}

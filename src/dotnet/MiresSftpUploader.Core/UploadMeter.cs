namespace MiresSftpUploader.Core;

/// <summary>
/// The one meter of a Run. Uploads report cumulative server-acknowledged bytes through an <see cref="IProgress{T}"/> that does no more
/// than an atomic write (it runs on the adapter's receive thread); a timer ticks about 4 times a second, samples the latest byte count
/// of every active file and emits one batched <see cref="UploadProgress"/>. Upload Speed is computed only here, over a sliding window.
/// </summary>
internal sealed class UploadMeter : IDisposable
{
    internal static readonly TimeSpan Interval = TimeSpan.FromMilliseconds(250);
    internal static readonly TimeSpan Window = TimeSpan.FromSeconds(3);

    private readonly TimeProvider _time;
    private readonly Action<RunEvent> _emit;
    private readonly object _gate = new();
    private readonly Dictionary<(string Source, string Path), Active> _active = new();
    private ITimer? _timer;
    private bool _emittedFiles;
    private bool _disposed;

    public UploadMeter(TimeProvider time, Action<RunEvent> emit)
    {
        _time = time;
        _emit = emit;
    }

    /// <summary>Starts metering a file or Archive attempt at 0 bytes (a retry replaces the earlier attempt). Dispose the result when the attempt ends.</summary>
    public Active Begin(string source, string path, long total)
    {
        var active = new Active(this, (source, path), total);
        lock (_gate)
        {
            if (_disposed) return active;
            _active[active.Key] = active;
            _timer ??= _time.CreateTimer(_ => Tick(), null, Interval, Interval);
        }
        return active;
    }

    private void Tick()
    {
        lock (_gate)
        {
            if (_disposed || _active.Count == 0) return;
            var now = _time.GetTimestamp();
            var files = new List<UploadingFile>(_active.Count);
            double? total = null;
            foreach (var a in _active.Values.OrderBy(a => a.Key.Source, StringComparer.Ordinal).ThenBy(a => a.Key.Path, StringComparer.Ordinal))
            {
                var speed = a.Sample(now, _time);
                if (speed is { } s) total = (total ?? 0) + s;
                files.Add(new UploadingFile(a.Key.Source, a.Key.Path, Math.Min(a.Bytes, a.Total), a.Total, speed));
            }
            _emittedFiles = true;
            _emit(new UploadProgress(files, total));
        }
    }

    private void End(Active active)
    {
        lock (_gate)
        {
            if (!_active.TryGetValue(active.Key, out var current) || !ReferenceEquals(current, active)) return;
            _active.Remove(active.Key);
            if (_active.Count > 0 || !_emittedFiles || _disposed) return;
            _emittedFiles = false;
            _emit(new UploadProgress([], null));
        }
    }

    public void Dispose()
    {
        ITimer? timer;
        lock (_gate)
        {
            _disposed = true;
            timer = _timer;
            _timer = null;
        }
        timer?.Dispose();
    }

    /// <summary>One file being uploaded. The sink is the progress parameter of <c>UploadAsync</c>.</summary>
    internal sealed class Active(UploadMeter meter, (string Source, string Path) key, long total) : IProgress<long>, IDisposable
    {
        private readonly Queue<(long Timestamp, long Bytes)> _samples = new();
        private long _bytes;

        public (string Source, string Path) Key { get; } = key;
        public long Total { get; } = total;
        public long Bytes => Volatile.Read(ref _bytes);

        /// <summary>An atomic write that keeps the maximum, so smaller or out-of-order reports never move the file backwards.</summary>
        public void Report(long value)
        {
            long seen;
            do
            {
                seen = Volatile.Read(ref _bytes);
                if (value <= seen) return;
            }
            while (Interlocked.CompareExchange(ref _bytes, value, seen) != seen);
        }

        /// <summary>Adds a sample and returns the Upload Speed over the window, or null while fewer than 2 samples exist.</summary>
        internal double? Sample(long now, TimeProvider time)
        {
            _samples.Enqueue((now, Bytes));
            while (_samples.Count > 2 && time.GetElapsedTime(_samples.Peek().Timestamp, now) > Window) _samples.Dequeue();
            if (_samples.Count < 2) return null;
            var first = _samples.Peek();
            var last = _samples.Last();
            var seconds = time.GetElapsedTime(first.Timestamp, last.Timestamp).TotalSeconds;
            return seconds <= 0 ? null : (last.Bytes - first.Bytes) / seconds;
        }

        public void Dispose() => meter.End(this);
    }
}

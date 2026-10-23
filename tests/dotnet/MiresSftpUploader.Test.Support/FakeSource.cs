using MiresSftpUploader.Core;

namespace MiresSftpUploader.Test.Support;

/// <summary>In-memory <see cref="ISource"/> holding files by relative path.</summary>
public sealed class FakeSource(string name, string? remotePath = null) : ISource
{
    private readonly Dictionary<string, (byte[] Data, DateTimeOffset Modified, string? ETag)> _files = new();

    public string Name { get; } = name;
    public string? RemotePath { get; } = remotePath;

    private int _openCount;

    /// <summary>Called after a file was opened for reading; lets a test change the file while it is being read.</summary>
    public Action<string>? AfterOpen { get; set; }

    /// <summary>Called when a listing has been delivered completely; lets a test change a file between scan and use.</summary>
    public Action? AfterListing { get; set; }

    /// <summary>How many times a file has been opened for reading.</summary>
    public int OpenCount => Volatile.Read(ref _openCount);

    /// <summary>Removes a file, as if it vanished from the Source.</summary>
    public FakeSource Remove(string relativePath)
    {
        _files.Remove(relativePath);
        return this;
    }

    public FakeSource Add(string relativePath, byte[] data, DateTimeOffset? modified = null, string? etag = null)
    {
        _files[relativePath] = (data, modified ?? new DateTimeOffset(2026, 1, 1, 0, 0, 0, TimeSpan.Zero), etag);
        return this;
    }

    public FakeSource Add(string relativePath, string text, DateTimeOffset modified, string? etag = null) =>
        Add(relativePath, System.Text.Encoding.UTF8.GetBytes(text), modified, etag);

    public FakeSource Add(string relativePath, string text) => Add(relativePath, System.Text.Encoding.UTF8.GetBytes(text));

    private int _listCount;

    /// <summary>How many times the Source has been listed (scanned).</summary>
    public int ListCount => Volatile.Read(ref _listCount);

    public async IAsyncEnumerable<SourceFile> ListAsync([System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken cancellationToken)
    {
        Interlocked.Increment(ref _listCount);
        foreach (var (path, entry) in _files.OrderBy(f => f.Key, StringComparer.Ordinal))
        {
            await Task.Yield();
            yield return new SourceFile(path, entry.Data.Length, entry.Modified, entry.ETag);
        }
        AfterListing?.Invoke();
    }

    public Task<SourceFile?> StatAsync(string relativePath, CancellationToken cancellationToken) =>
        Task.FromResult<SourceFile?>(_files.TryGetValue(relativePath, out var entry)
            ? new SourceFile(relativePath, entry.Data.Length, entry.Modified, entry.ETag)
            : null);

    public Task<Stream> OpenReadAsync(string relativePath, CancellationToken cancellationToken)
    {
        var stream = Opened(_files[relativePath].Data);
        AfterOpen?.Invoke(relativePath);
        return Task.FromResult<Stream>(stream);
    }

    private readonly Dictionary<string, byte[]> _moved = new(StringComparer.Ordinal);
    private readonly object _moveGate = new();

    /// <summary>Makes a move fail with this result instead of happening (receives the relative path); null lets it happen.</summary>
    public Func<string, MoveResult?>? MoveInterceptor { get; set; }

    /// <summary>The relative paths moved away, in order.</summary>
    public List<string> MovedPaths { get; } = [];

    private static string TargetKey(MoveTargetConfig target, string relativePath) =>
        (target.Path ?? $"{target.Bucket}/{target.Prefix}").TrimEnd('/') + "/" + relativePath;

    /// <summary>A file in a move target, or null.</summary>
    public byte[]? MovedFile(MoveTargetConfig target, string relativePath)
    {
        lock (_moveGate) return _moved.GetValueOrDefault(TargetKey(target, relativePath));
    }

    public void PutMoved(MoveTargetConfig target, string relativePath, byte[] data)
    {
        lock (_moveGate) _moved[TargetKey(target, relativePath)] = data;
    }

    public Task<MoveResult> MoveAsync(string relativePath, MoveTargetConfig target, CancellationToken cancellationToken)
    {
        lock (_moveGate)
        {
            if (MoveInterceptor?.Invoke(relativePath) is { } injected) return Task.FromResult(injected);
            if (!_files.TryGetValue(relativePath, out var entry)) return Task.FromResult(MoveResult.Failed("no such file"));
            var key = TargetKey(target, relativePath);
            if (_moved.ContainsKey(key)) return Task.FromResult(MoveResult.TargetExists(key));
            _moved[key] = entry.Data;
            _files.Remove(relativePath);
            MovedPaths.Add(relativePath);
            return Task.FromResult(MoveResult.Moved());
        }
    }

    private MemoryStream Opened(byte[] data)
    {
        Interlocked.Increment(ref _openCount);
        return new MemoryStream(data, writable: false);
    }
}

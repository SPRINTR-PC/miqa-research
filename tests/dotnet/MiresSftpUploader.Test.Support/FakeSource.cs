using MiresSftpUploader.Core;

namespace MiresSftpUploader.Test.Support;

/// <summary>In-memory <see cref="ISource"/> holding files by relative path.</summary>
public sealed class FakeSource(string name, string? remotePath = null) : ISource
{
    private readonly Dictionary<string, (byte[] Data, DateTimeOffset Modified)> _files = new();

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

    public FakeSource Add(string relativePath, byte[] data, DateTimeOffset? modified = null)
    {
        _files[relativePath] = (data, modified ?? new DateTimeOffset(2026, 1, 1, 0, 0, 0, TimeSpan.Zero));
        return this;
    }

    public FakeSource Add(string relativePath, string text, DateTimeOffset modified) =>
        Add(relativePath, System.Text.Encoding.UTF8.GetBytes(text), modified);

    public FakeSource Add(string relativePath, string text) => Add(relativePath, System.Text.Encoding.UTF8.GetBytes(text));

    public async IAsyncEnumerable<SourceFile> ListAsync([System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken cancellationToken)
    {
        foreach (var (path, entry) in _files.OrderBy(f => f.Key, StringComparer.Ordinal))
        {
            await Task.Yield();
            yield return new SourceFile(path, entry.Data.Length, entry.Modified);
        }
        AfterListing?.Invoke();
    }

    public Task<SourceFile?> StatAsync(string relativePath, CancellationToken cancellationToken) =>
        Task.FromResult<SourceFile?>(_files.TryGetValue(relativePath, out var entry)
            ? new SourceFile(relativePath, entry.Data.Length, entry.Modified)
            : null);

    public Task<Stream> OpenReadAsync(string relativePath, CancellationToken cancellationToken)
    {
        var stream = Opened(_files[relativePath].Data);
        AfterOpen?.Invoke(relativePath);
        return Task.FromResult<Stream>(stream);
    }

    private MemoryStream Opened(byte[] data)
    {
        Interlocked.Increment(ref _openCount);
        return new MemoryStream(data, writable: false);
    }
}

using System.Runtime.CompilerServices;

namespace MiresSftpUploader.Core;

/// <summary>A Source backed by a local directory. Symlinks (to files or directories) are not followed.</summary>
public sealed class DirectorySource(string name, string path, string? remotePath = null) : ISource
{
    public string Name { get; } = name;
    public string? RemotePath { get; } = remotePath;

    public async IAsyncEnumerable<SourceFile> ListAsync([EnumeratorCancellation] CancellationToken cancellationToken)
    {
        var pending = new Stack<(DirectoryInfo Dir, string Prefix)>();
        pending.Push((new DirectoryInfo(path), ""));

        while (pending.Count > 0)
        {
            cancellationToken.ThrowIfCancellationRequested();
            var (dir, prefix) = pending.Pop();
            foreach (var entry in dir.EnumerateFileSystemInfos())
            {
                if (IsLink(entry)) continue;
                var relative = prefix + entry.Name;
                if (entry is DirectoryInfo sub)
                    pending.Push((sub, relative + "/"));
                else if (entry is FileInfo file)
                    yield return new SourceFile(relative, file.Length, new DateTimeOffset(file.LastWriteTimeUtc, TimeSpan.Zero));
            }
            await Task.Yield();
        }
    }

    public Task<SourceFile?> StatAsync(string relativePath, CancellationToken cancellationToken)
    {
        var file = new FileInfo(Path.Combine(path, relativePath.Replace('/', Path.DirectorySeparatorChar)));
        return Task.FromResult<SourceFile?>(file.Exists && !IsLink(file)
            ? new SourceFile(relativePath, file.Length, new DateTimeOffset(file.LastWriteTimeUtc, TimeSpan.Zero))
            : null);
    }

    public Task<Stream> OpenReadAsync(string relativePath, CancellationToken cancellationToken)
    {
        var full = Path.Combine(path, relativePath.Replace('/', Path.DirectorySeparatorChar));
        Stream stream = new FileStream(full, FileMode.Open, FileAccess.Read, FileShare.Read, 81920, FileOptions.Asynchronous | FileOptions.SequentialScan);
        return Task.FromResult(stream);
    }

    private static bool IsLink(FileSystemInfo entry) =>
        entry.LinkTarget is not null || entry.Attributes.HasFlag(FileAttributes.ReparsePoint);
}

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

    public Task<MoveResult> MoveAsync(string relativePath, MoveTargetConfig target, CancellationToken cancellationToken)
    {
        try
        {
            var from = FullPath(relativePath);
            var to = Path.Combine(target.Path!, relativePath.Replace('/', Path.DirectorySeparatorChar));
            if (!File.Exists(from)) return Task.FromResult(MoveResult.Failed("the file is no longer in the Source"));
            if (File.Exists(to) || Directory.Exists(to)) return Task.FromResult(MoveResult.TargetExists(to));
            Directory.CreateDirectory(Path.GetDirectoryName(to)!);

            if (!SameVolume(from, to)) return Task.FromResult(MoveByCopy(from, to));
            try
            {
                File.Move(from, to, overwrite: false);
                return Task.FromResult(MoveResult.Moved());
            }
            catch (IOException) when (File.Exists(to))
            {
                return Task.FromResult(MoveResult.TargetExists(to));
            }
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            return Task.FromResult(MoveResult.Failed(ex.Message));
        }
    }

    /// <summary>
    /// Copy to a temporary name beside the target, check the length, rename into place (never over an existing file),
    /// and only then delete the original. Used when the target is on another volume.
    /// </summary>
    internal static MoveResult MoveByCopy(string from, string to)
    {
        var temporary = to + ".mires-move.part";
        try
        {
            var length = new FileInfo(from).Length;
            using (var source = new FileStream(from, FileMode.Open, FileAccess.Read, FileShare.Read, 81920, FileOptions.SequentialScan))
            using (var destination = new FileStream(temporary, FileMode.Create, FileAccess.Write, FileShare.None, 81920))
                source.CopyTo(destination);

            var copied = new FileInfo(temporary).Length;
            if (copied != length)
            {
                File.Delete(temporary);
                return MoveResult.Failed($"the copy has {copied} bytes, expected {length}");
            }
            File.SetLastWriteTimeUtc(temporary, File.GetLastWriteTimeUtc(from));
            try
            {
                File.Move(temporary, to, overwrite: false);
            }
            catch (IOException) when (File.Exists(to))
            {
                File.Delete(temporary);
                return MoveResult.TargetExists(to);
            }
            File.Delete(from);
            return MoveResult.Moved();
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            try { File.Delete(temporary); } catch (Exception cleanup) when (cleanup is IOException or UnauthorizedAccessException) { }
            return MoveResult.Failed(ex.Message);
        }
    }

    private string FullPath(string relativePath) => Path.Combine(path, relativePath.Replace('/', Path.DirectorySeparatorChar));

    /// <summary>
    /// Whether both paths are on the same mounted volume (longest mount point wins). When in doubt it says false, which only
    /// costs a copy instead of a rename.
    /// </summary>
    private static bool SameVolume(string a, string b)
    {
        try
        {
            static string? Mount(string p)
            {
                var full = Path.GetFullPath(p);
                return DriveInfo.GetDrives()
                    .Select(d => d.RootDirectory.FullName)
                    .Where(root => full.StartsWith(root, StringComparison.OrdinalIgnoreCase))
                    .OrderByDescending(root => root.Length)
                    .FirstOrDefault();
            }
            var (x, y) = (Mount(a), Mount(b));
            return x is not null && x == y;
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            return false;
        }
    }

    private static bool IsLink(FileSystemInfo entry) =>
        entry.LinkTarget is not null || entry.Attributes.HasFlag(FileAttributes.ReparsePoint);
}

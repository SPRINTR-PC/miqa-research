namespace MiresSftpUploader.Core;

/// <summary>
/// One file found in a Source. <see cref="RelativePath"/> uses forward slashes. <see cref="ETag"/> is set by S3 Sources
/// only; it is a version identifier, never a content hash.
/// </summary>
public sealed record SourceFile(string RelativePath, long Size, DateTimeOffset Modified, string? ETag = null)
{
    /// <summary>
    /// What the Upload State stores to tell versions of a file apart (together with <see cref="Size"/>): the modified time
    /// for a Directory Source, a stable 63-bit digest of the ETag for an S3 Source.
    /// </summary>
    public long ChangeToken => ETag is null
        ? Modified.UtcTicks
        : (long)(BitConverter.ToUInt64(System.Security.Cryptography.SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(ETag))) >> 1);
}

/// <summary>The seam to where a Source's files live: a local directory or an S3-compatible bucket prefix.</summary>
public interface ISource
{
    string Name { get; }

    /// <summary>Remote Path override; null means the configured remote root plus the Source name.</summary>
    string? RemotePath { get; }

    /// <summary>Lists every file recursively. Symlinks are not followed.</summary>
    IAsyncEnumerable<SourceFile> ListAsync(CancellationToken cancellationToken);

    /// <summary>Describes one file without listing the Source; null when it is no longer there. Used to retry failed files,
    /// and by the Engine to notice a file that changed while it was uploaded.</summary>
    Task<SourceFile?> StatAsync(string relativePath, CancellationToken cancellationToken);

    Task<Stream> OpenReadAsync(string relativePath, CancellationToken cancellationToken);
}

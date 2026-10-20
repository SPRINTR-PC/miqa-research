namespace MiresSftpUploader.Core;

/// <summary>One file found in a Source. <see cref="RelativePath"/> uses forward slashes.</summary>
public sealed record SourceFile(string RelativePath, long Size, DateTimeOffset Modified);

/// <summary>The seam to where a Source's files live: a local directory or an S3-compatible bucket prefix.</summary>
public interface ISource
{
    string Name { get; }

    /// <summary>Remote Path override; null means the configured remote root plus the Source name.</summary>
    string? RemotePath { get; }

    /// <summary>Lists every file recursively. Symlinks are not followed.</summary>
    IAsyncEnumerable<SourceFile> ListAsync(CancellationToken cancellationToken);

    /// <summary>Describes one file without listing the Source; null when it is no longer there. Used to retry failed files.</summary>
    Task<SourceFile?> StatAsync(string relativePath, CancellationToken cancellationToken);

    Task<Stream> OpenReadAsync(string relativePath, CancellationToken cancellationToken);
}

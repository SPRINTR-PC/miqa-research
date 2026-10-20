namespace MiresSftpUploader.Core;

/// <summary>The seam to the SFTP server. One adapter talks SSH.NET; another is an in-memory fake.</summary>
public interface IRemote
{
    /// <summary>Opens one session (one per upload worker). Host key pinning is checked here.</summary>
    Task<RemoteResult<IRemoteSession>> ConnectAsync(CancellationToken cancellationToken);
}

public interface IRemoteSession : IAsyncDisposable
{
    /// <summary>Creates the directory and any missing parents; Ok if it already exists.</summary>
    Task<RemoteResult> EnsureDirectoryAsync(string path, CancellationToken cancellationToken);

    /// <summary>Writes the stream to <paramref name="path"/>, replacing any existing object. Reads the stream to its end exactly once.</summary>
    Task<RemoteResult> UploadAsync(Stream content, string path, CancellationToken cancellationToken);

    Task<RemoteResult> RenameAsync(string from, string to, bool overwrite, CancellationToken cancellationToken);

    Task<RemoteResult> DeleteAsync(string path, CancellationToken cancellationToken);

    /// <summary>Ok with the info when the object exists, Failed("not found") otherwise.</summary>
    Task<RemoteResult<RemoteFileInfo>> StatAsync(string path, CancellationToken cancellationToken);
}

namespace MiresSftpUploader.Core;

/// <summary>What the window and the Headless Run call: run once. Implemented by <see cref="Engine"/>; view-model tests use a fake.</summary>
public interface IRunEngine
{
    Task<RunResult> RunAsync(RunOptions options, IProgress<RunEvent> progress, CancellationToken cancellationToken);
}

/// <summary>Builds the <see cref="IRemote"/> for a Run from the configuration and the Secrets read at its start.</summary>
public interface IRemoteFactory
{
    IRemote Create(AppConfig config, Secrets secrets);
}

/// <summary>Builds the <see cref="ISource"/> of one configured Source.</summary>
public interface ISourceFactory
{
    ISource Create(SourceConfig config, Secrets secrets);
}

/// <summary>
/// Stands in for the SFTP adapter until it is plugged in: every connection fails with a message that says so,
/// which a Run reports as exit code 3.
/// </summary>
public sealed class UnavailableRemoteFactory : IRemoteFactory
{
    public const string Message = "The SFTP adapter is not available in this build.";

    public IRemote Create(AppConfig config, Secrets secrets) => new UnavailableRemote();

    private sealed class UnavailableRemote : IRemote
    {
        public Task<RemoteResult<IRemoteSession>> ConnectAsync(CancellationToken cancellationToken) =>
            Task.FromResult(RemoteResult<IRemoteSession>.Failed(Message));
    }
}

/// <summary>Local directories only; an S3 Source is not available until its adapter is plugged in, and fails the Run with a clear message.</summary>
public sealed class DefaultSourceFactory : ISourceFactory
{
    public const string S3Message = "S3 Sources are not available in this build.";

    public ISource Create(SourceConfig config, Secrets secrets) =>
        config.Type == SourceType.Directory
            ? new DirectorySource(config.Name!, config.Path!, config.RemotePath)
            : new UnavailableSource(config.Name!, config.RemotePath, S3Message);

    private sealed class UnavailableSource(string name, string? remotePath, string message) : ISource
    {
        public string Name { get; } = name;
        public string? RemotePath { get; } = remotePath;
        public IAsyncEnumerable<SourceFile> ListAsync(CancellationToken cancellationToken) => throw new NotSupportedException(message);
        public Task<SourceFile?> StatAsync(string relativePath, CancellationToken cancellationToken) => throw new NotSupportedException(message);
        public Task<Stream> OpenReadAsync(string relativePath, CancellationToken cancellationToken) => throw new NotSupportedException(message);
    }
}

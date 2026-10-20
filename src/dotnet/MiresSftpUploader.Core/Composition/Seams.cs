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

/// <summary>The SSH.NET adapter: connects with the configured Destination, the pinned Host Key Fingerprint and the Secrets.</summary>
public sealed class SshNetRemoteFactory : IRemoteFactory
{
    public IRemote Create(AppConfig config, Secrets secrets) => new SshNetRemote(SftpConnection.From(config.Sftp, secrets));
}

/// <summary>
/// A remote for tests and builds without an SFTP adapter: every connection fails with a message that says so,
/// which a Run reports as exit code 3.
/// </summary>
public sealed class UnavailableRemoteFactory : IRemoteFactory
{
    public const string Message = "No SFTP adapter is configured.";

    public IRemote Create(AppConfig config, Secrets secrets) => new UnavailableRemote();

    private sealed class UnavailableRemote : IRemote
    {
        public Task<RemoteResult<IRemoteSession>> ConnectAsync(CancellationToken cancellationToken) =>
            Task.FromResult(RemoteResult<IRemoteSession>.Failed(Message));
    }
}

/// <summary>The production <see cref="ISourceFactory"/>: a Directory or an S3 Source (see <see cref="SourceFactory"/>).</summary>
public sealed class DefaultSourceFactory : ISourceFactory
{
    /// <exception cref="SourceSetupException">An S3 Source's Secrets are not set.</exception>
    public ISource Create(SourceConfig config, Secrets secrets) => SourceFactory.Create(config, secrets);
}

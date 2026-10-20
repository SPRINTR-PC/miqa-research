using Renci.SshNet;
using Renci.SshNet.Common;

namespace MiresSftpUploader.Core;

/// <summary>Everything the SFTP adapter needs to open a session. Secrets arrive here already read from the environment.</summary>
public sealed record SftpConnection
{
    public required string Host { get; init; }
    public int Port { get; init; } = 22;
    public required string Username { get; init; }
    public AuthMethod AuthMethod { get; init; } = AuthMethod.Password;
    public string? Password { get; init; }
    public string? PrivateKeyPath { get; init; }
    public string? PrivateKeyPassphrase { get; init; }
    /// <summary>The pinned Host Key Fingerprint; a <c>SHA256:</c> or <c>MD5:</c> prefix is accepted.</summary>
    public required string HostKeyFingerprint { get; init; }
    public TimeSpan ConnectTimeout { get; init; } = TimeSpan.FromSeconds(30);
    /// <summary>Zero turns keep-alive off.</summary>
    public TimeSpan KeepAlive { get; init; } = TimeSpan.FromSeconds(30);

    public override string ToString() => $"{Username}@{Host}:{Port}";
}

/// <summary>The SSH.NET adapter of <see cref="IRemote"/>: one <c>SftpClient</c> (one connection) per session.</summary>
public sealed class SshNetRemote(SftpConnection connection) : IRemote
{
    public async Task<RemoteResult<IRemoteSession>> ConnectAsync(CancellationToken cancellationToken)
    {
        var session = new Session(connection);
        var connected = await session.ConnectAsync(cancellationToken);
        if (connected.IsOk) return RemoteResult<IRemoteSession>.Ok(session);
        await session.DisposeAsync();
        return new RemoteResult<IRemoteSession>(connected.Kind, default, connected.Reason);
    }

    private sealed class Session(SftpConnection settings) : IRemoteSession
    {
        private readonly HashSet<string> _knownDirectories = new(StringComparer.Ordinal);
        private SftpClient? _client;

        /// <summary>Opens the connection, checking the host key before any credential is sent.</summary>
        public async Task<RemoteResult> ConnectAsync(CancellationToken ct)
        {
            _client?.Dispose();
            _client = null;

            string? mismatch = null;
            SftpClient client;
            try
            {
                client = new SftpClient(BuildConnectionInfo(settings)) { KeepAliveInterval = settings.KeepAlive };
            }
            catch (Exception ex) when (ex is IOException or SshException or ArgumentException)
            {
                return RemoteResult.Failed($"Cannot use the private key: {ex.Message}");
            }

            client.HostKeyReceived += (_, e) =>
            {
                e.CanTrust = HostKeyFingerprint.Matches(settings.HostKeyFingerprint, e.FingerPrintSHA256, e.FingerPrintMD5);
                if (!e.CanTrust) mismatch = $"Host key mismatch: {settings} presented SHA256:{e.FingerPrintSHA256} ({e.HostKeyName}), which is not the pinned Host Key Fingerprint.";
            };

            try
            {
                await client.ConnectAsync(ct);
            }
            catch (OperationCanceledException)
            {
                client.Dispose();
                throw;
            }
            catch (SshAuthenticationException ex)
            {
                client.Dispose();
                return RemoteResult.Denied($"Authentication failed for {settings}: {ex.Message}");
            }
            catch (Exception ex) when (ex is SshException or IOException or System.Net.Sockets.SocketException or TimeoutException or InvalidOperationException)
            {
                client.Dispose();
                return RemoteResult.Failed(mismatch ?? $"Cannot connect to {settings}: {ex.Message}");
            }

            if (mismatch is not null)
            {
                client.Dispose();
                return RemoteResult.Failed(mismatch);
            }

            _client = client;
            _knownDirectories.Clear();
            return RemoteResult.Ok;
        }

        private static ConnectionInfo BuildConnectionInfo(SftpConnection s)
        {
            AuthenticationMethod method = s.AuthMethod == AuthMethod.PrivateKey
                ? new PrivateKeyAuthenticationMethod(s.Username, new PrivateKeyFile(s.PrivateKeyPath!, s.PrivateKeyPassphrase))
                : new PasswordAuthenticationMethod(s.Username, s.Password ?? "");
            return new ConnectionInfo(s.Host, s.Port, s.Username, method) { Timeout = s.ConnectTimeout };
        }

        /// <summary>Runs one operation, first re-opening the connection if a previous failure dropped it.</summary>
        private async Task<RemoteResult<T>> RunAsync<T>(Func<SftpClient, Task<T>> operation, CancellationToken ct)
        {
            if (_client is not { IsConnected: true })
            {
                var reconnected = await ConnectAsync(ct);
                if (!reconnected.IsOk) return new RemoteResult<T>(reconnected.Kind, default, reconnected.Reason);
            }

            try
            {
                return RemoteResult<T>.Ok(await operation(_client!));
            }
            catch (OperationCanceledException)
            {
                throw;
            }
            catch (SftpPermissionDeniedException ex)
            {
                return RemoteResult<T>.Denied(ex.Message);
            }
            catch (SftpPathNotFoundException ex)
            {
                return RemoteResult<T>.Failed($"not found: {ex.Message}");
            }
            catch (Exception ex) when (ex is SshException or IOException or NotSupportedException or System.Net.Sockets.SocketException or ObjectDisposedException)
            {
                return RemoteResult<T>.Failed(ex.Message);
            }
        }

        private async Task<RemoteResult> RunAsync(Func<SftpClient, Task> operation, CancellationToken ct) =>
            (await RunAsync<bool>(async c => { await operation(c); return true; }, ct)).WithoutValue();

        public Task<RemoteResult> EnsureDirectoryAsync(string path, CancellationToken ct) =>
            RunAsync(client => Task.Run(() =>
            {
                var current = "";
                foreach (var part in path.Split('/', StringSplitOptions.RemoveEmptyEntries))
                {
                    current += "/" + part;
                    if (_knownDirectories.Contains(current)) continue;
                    try
                    {
                        client.CreateDirectory(current);
                    }
                    catch (Exception ex) when (ex is SshException)
                    {
                        // A directory that already exists makes the create fail; a server that forbids the stat
                        // (a drop-box) reports the original error.
                        if (!IsExistingDirectory(client, current)) throw;
                    }
                    _knownDirectories.Add(current);
                }
            }, ct), ct);

        private static bool IsExistingDirectory(SftpClient client, string path)
        {
            try
            {
                return client.GetAttributes(path).IsDirectory;
            }
            catch (SshException)
            {
                return false;
            }
        }

        public Task<RemoteResult> UploadAsync(Stream content, string path, CancellationToken ct) =>
            RunAsync(client => client.UploadFileAsync(content, path, ct), ct);

        public Task<RemoteResult> RenameAsync(string from, string to, bool overwrite, CancellationToken ct) =>
            RunAsync(client => Task.Run(() =>
            {
                try
                {
                    client.RenameFile(from, to, isPosix: overwrite);
                }
                catch (NotSupportedException)
                {
                    throw new NotSupportedException("The server does not offer posix-rename@openssh.com, so the .part file cannot replace an existing file atomically.");
                }
            }, ct), ct);

        public Task<RemoteResult> DeleteAsync(string path, CancellationToken ct) =>
            RunAsync(client => Task.Run(() => client.DeleteFile(path), ct), ct);

        public Task<RemoteResult<RemoteFileInfo>> StatAsync(string path, CancellationToken ct) =>
            RunAsync(client => Task.Run(() => new RemoteFileInfo(client.GetAttributes(path).Size), ct), ct);

        public ValueTask DisposeAsync()
        {
            _client?.Dispose();
            _client = null;
            return ValueTask.CompletedTask;
        }
    }
}

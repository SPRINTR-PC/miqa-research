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

    /// <summary>Joins the validated configuration with the Secrets from the environment.</summary>
    public static SftpConnection From(SftpConfig sftp, Secrets secrets) => new()
    {
        Host = sftp.Host!,
        Port = sftp.Port,
        Username = sftp.Username!,
        AuthMethod = sftp.AuthMethod,
        Password = secrets.SftpPassword,
        PrivateKeyPath = sftp.PrivateKeyPath,
        PrivateKeyPassphrase = secrets.SftpKeyPassphrase,
        HostKeyFingerprint = sftp.HostKeyFingerprint!,
        ConnectTimeout = TimeSpan.FromSeconds(sftp.ConnectTimeoutSeconds),
        KeepAlive = TimeSpan.FromSeconds(sftp.KeepAliveSeconds),
    };

    // Never prints the secrets.
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
                // Not Denied, even for a rejected login: Denied means "this account may not do that" and is permanent for the file,
                // while a connection that cannot be re-opened mid-Run is a failure of the connection and is retried.
                if (!reconnected.IsOk) return RemoteResult<T>.Failed("Could not reconnect: " + reconnected.Reason);
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

        public Task<RemoteResult> UploadAsync(Stream content, string path, CancellationToken ct, IProgress<long>? progress = null) =>
            progress is null
                ? RunAsync(client => client.UploadFileAsync(content, path, ct), ct)
                : RunAsync(client => client.UploadFileAsync(content, path, canOverride: true, new AcknowledgedBytes(progress), ct), ct);

        /// <summary>
        /// Runs inline on SSH.NET's receive thread, about once per 32 KiB, and the reports can arrive out of order: it keeps the
        /// maximum total reported and does nothing else.
        /// </summary>
        private sealed class AcknowledgedBytes(IProgress<long> sink) : IProgress<UploadFileProgressReport>
        {
            private long _max;

            public void Report(UploadFileProgressReport value)
            {
                var total = (long)Math.Min(value.TotalBytesUploaded, long.MaxValue);
                long seen;
                do
                {
                    seen = Volatile.Read(ref _max);
                    if (total <= seen) return;
                }
                while (Interlocked.CompareExchange(ref _max, total, seen) != seen);
                sink.Report(total);
            }
        }

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

        public Task<RemoteResult<IReadOnlyList<string>>> ListAsync(string directory, CancellationToken ct) =>
            RunAsync<IReadOnlyList<string>>(client => Task.Run(() =>
                (IReadOnlyList<string>)client.ListDirectory(directory).Select(e => e.Name).Where(n => n is not ("." or "..")).ToList(), ct), ct);

        public Task<RemoteResult<RemoteFileInfo>> StatAsync(string path, CancellationToken ct) =>
            RunAsync(client => Task.Run(() => new RemoteFileInfo(client.GetAttributes(path).Size), ct), ct);

        public Task<RemoteResult> DownloadAsync(string path, Stream destination, CancellationToken ct) =>
            RunAsync(client => Task.Run(() => client.DownloadFile(path, destination), ct), ct);

        public async Task<RemoteResult<string>> RunCommandAsync(string command, CancellationToken ct)
        {
            try
            {
                var ssh = await ShellAsync(ct);
                if (ssh.Value is null) return new RemoteResult<string>(ssh.Kind, default, ssh.Reason);
                return await Task.Run(() =>
                {
                    using var run = ssh.Value.CreateCommand(command);
                    var output = run.Execute();
                    return run.ExitStatus == 0
                        ? RemoteResult<string>.Ok(output)
                        : RemoteResult<string>.Failed($"exit status {run.ExitStatus}: {run.Error.Trim()}".TrimEnd(' ', ':'));
                }, ct);
            }
            catch (Exception ex) when (ex is SshException or IOException or System.Net.Sockets.SocketException or InvalidOperationException or ObjectDisposedException)
            {
                // An SFTP-only account refuses the exec request (ForceCommand internal-sftp, a restricted shell, no shell at all).
                _shell?.Dispose();
                _shell = null;
                return RemoteResult<string>.Failed("The server does not run commands for this account: " + ex.Message);
            }
        }

        private SshClient? _shell;

        /// <summary>A second connection of the same account for command execution; SFTP and exec channels need an <c>SshClient</c>.</summary>
        private async Task<RemoteResult<SshClient>> ShellAsync(CancellationToken ct)
        {
            if (_shell is { IsConnected: true }) return RemoteResult<SshClient>.Ok(_shell);
            _shell?.Dispose();
            string? mismatch = null;
            var shell = new SshClient(BuildConnectionInfo(settings)) { KeepAliveInterval = settings.KeepAlive };
            shell.HostKeyReceived += (_, e) =>
            {
                e.CanTrust = HostKeyFingerprint.Matches(settings.HostKeyFingerprint, e.FingerPrintSHA256, e.FingerPrintMD5);
                if (!e.CanTrust) mismatch = $"Host key mismatch: {settings} presented SHA256:{e.FingerPrintSHA256}, which is not the pinned Host Key Fingerprint.";
            };
            try
            {
                await shell.ConnectAsync(ct);
            }
            catch (Exception ex) when (ex is SshException or IOException or System.Net.Sockets.SocketException or TimeoutException)
            {
                shell.Dispose();
                return RemoteResult<SshClient>.Failed(mismatch ?? $"Cannot open a command connection to {settings}: {ex.Message}");
            }
            _shell = shell;
            return RemoteResult<SshClient>.Ok(shell);
        }

        public ValueTask DisposeAsync()
        {
            _shell?.Dispose();
            _shell = null;
            _client?.Dispose();
            _client = null;
            return ValueTask.CompletedTask;
        }
    }
}

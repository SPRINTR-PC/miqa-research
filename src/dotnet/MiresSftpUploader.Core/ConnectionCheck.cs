namespace MiresSftpUploader.Core;

public enum ConnectionCheckOutcome { Connected, InvalidConfiguration, MissingCredentials, Failed, HostKeyNotTrusted }

/// <summary>What a connection check found. <see cref="Message"/> is human-readable (several lines for an invalid configuration).</summary>
public sealed record ConnectionCheckResult(ConnectionCheckOutcome Outcome, string Message)
{
    public bool IsConnected => Outcome == ConnectionCheckOutcome.Connected;

    /// <summary>The process exit code <c>--validate-config --check-connection</c> ends with.</summary>
    public int ExitCode => Outcome switch
    {
        ConnectionCheckOutcome.Connected => ExitCodes.Ok,
        ConnectionCheckOutcome.Failed => ExitCodes.ConnectFailed,
        _ => ExitCodes.ConfigurationError,
    };
}

/// <summary>
/// Opens one session to prove the server answers, the presented host key matches the pinned Host Key Fingerprint and the credentials
/// (environment or Secret Store) work. Never uploads. Shared by <c>--validate-config --check-connection</c> and the Settings TUI's F5.
/// </summary>
public static class ConnectionCheck
{
    /// <summary>Checks the configuration as saved on disk (what a Headless Run would use).</summary>
    /// <param name="options">The command line the process was started with (<c>--data-dir</c>, <c>--log-level</c>); null means none.</param>
    public static Task<ConnectionCheckResult> CheckSavedAsync(Configuration configuration, Func<SftpConnection, IRemote> remoteFactory, CancellationToken cancellationToken, CliOptions? options = null)
    {
        var load = configuration.Load(options ?? new CliOptions(), headless: true);
        if (load.Config is not { } config || load.Errors.Count > 0)
        {
            var lines = load.Errors.Select(e => e.ToString());
            return Task.FromResult(new ConnectionCheckResult(ConnectionCheckOutcome.InvalidConfiguration,
                $"The saved configuration has {load.Errors.Count} error(s):\n" + string.Join("\n", lines)));
        }

        return RunAsync(config.Sftp, configuration.LoadSecrets(), remoteFactory, cancellationToken);
    }

    /// <summary>
    /// Like <see cref="RunAsync"/>, but works without a Host Key Fingerprint. When <paramref name="sftp"/> has none, the server's host key
    /// is read first (no credential is sent), <paramref name="confirm"/> asks the user whether it is the right one and, on yes,
    /// <paramref name="pin"/> receives the fingerprint to store; the check then continues pinned to it, so the credentials are still
    /// only ever sent to a host the user accepted. On no, nothing is stored and nothing but the key exchange happened.
    /// Callers that touch a UI in the callbacks should not run this on a thread-pool thread: the callbacks run on the caller's context.
    /// </summary>
    public static async Task<ConnectionCheckResult> RunPinningAsync(SftpConfig sftp, Secrets secrets, Func<SftpConnection, IRemote> remoteFactory,
        Func<SftpConfig, CancellationToken, Task<RemoteResult<PresentedHostKey>>> probe, Func<PresentedHostKey, Task<bool>> confirm,
        Action<string> pin, CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(sftp.Host))
            return new ConnectionCheckResult(ConnectionCheckOutcome.InvalidConfiguration, "Sftp:Host is not set.");
        if (string.IsNullOrWhiteSpace(sftp.Username))
            return new ConnectionCheckResult(ConnectionCheckOutcome.InvalidConfiguration, "Sftp:Username is not set.");

        var note = "";
        if (string.IsNullOrWhiteSpace(sftp.HostKeyFingerprint))
        {
            var probed = await probe(sftp, cancellationToken);
            if (!probed.IsOk)
                return new ConnectionCheckResult(ConnectionCheckOutcome.Failed, $"Could not read the host key of {sftp.Host}:{sftp.Port}: {probed.Reason}");

            var key = probed.Value!;
            if (!await confirm(key))
                return new ConnectionCheckResult(ConnectionCheckOutcome.HostKeyNotTrusted,
                    "The host key was not accepted. The Host Key Fingerprint is still not set and no credentials were sent.");

            pin(key.Fingerprint);
            sftp = sftp with { HostKeyFingerprint = key.Sha256 };
            note = $"Host Key Fingerprint set to {key.Fingerprint}. ";
        }

        var result = await RunAsync(sftp, secrets, remoteFactory, cancellationToken);
        return result with { Message = note + result.Message };
    }

    public static async Task<ConnectionCheckResult> RunAsync(SftpConfig sftp, Secrets secrets, Func<SftpConnection, IRemote> remoteFactory, CancellationToken cancellationToken)
    {
        if (sftp.AuthMethod != AuthMethod.PrivateKey && secrets.SftpPassword is null)
            return new ConnectionCheckResult(ConnectionCheckOutcome.MissingCredentials, secrets.SftpPasswordUnreadable
                ? "The stored sftp-password is unreadable on this machine (the machine or account changed since it was stored). Re-enter it with --set-secret sftp-password, or set " + Secrets.SftpPasswordVariable + "."
                : $"{Secrets.SftpPasswordVariable} is not set. Set it as an environment variable, or store it with --set-secret sftp-password.");

        var connection = SftpConnection.From(sftp, secrets);
        var connect = await remoteFactory(connection).ConnectAsync(cancellationToken).ConfigureAwait(false);
        if (!connect.IsOk)
            return new ConnectionCheckResult(ConnectionCheckOutcome.Failed, Redactor.From(secrets).Redact($"Connection check failed for {connection}: {connect.Reason}"));

        await connect.Value!.DisposeAsync().ConfigureAwait(false);
        return new ConnectionCheckResult(ConnectionCheckOutcome.Connected,
            $"Configuration is valid. Connected to {connection}; the host key matches the pinned Host Key Fingerprint.");
    }
}

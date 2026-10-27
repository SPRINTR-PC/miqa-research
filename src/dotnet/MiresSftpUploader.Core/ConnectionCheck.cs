namespace MiresSftpUploader.Core;

public enum ConnectionCheckOutcome { Connected, InvalidConfiguration, MissingCredentials, Failed }

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

    public static async Task<ConnectionCheckResult> RunAsync(SftpConfig sftp, Secrets secrets, Func<SftpConnection, IRemote> remoteFactory, CancellationToken cancellationToken)
    {
        if (sftp.AuthMethod != AuthMethod.PrivateKey && secrets.SftpPassword is null)
            return new ConnectionCheckResult(ConnectionCheckOutcome.MissingCredentials,
                $"{Secrets.SftpPasswordVariable} is not set. Set it as an environment variable, or store it with --set-secret sftp-password.");

        var connection = SftpConnection.From(sftp, secrets);
        var connect = await remoteFactory(connection).ConnectAsync(cancellationToken).ConfigureAwait(false);
        if (!connect.IsOk)
            return new ConnectionCheckResult(ConnectionCheckOutcome.Failed, Redactor.From(secrets).Redact($"Connection check failed for {connection}: {connect.Reason}"));

        await connect.Value!.DisposeAsync().ConfigureAwait(false);
        return new ConnectionCheckResult(ConnectionCheckOutcome.Connected,
            $"Configuration is valid. Connected to {connection}; the host key matches the pinned Host Key Fingerprint.");
    }
}

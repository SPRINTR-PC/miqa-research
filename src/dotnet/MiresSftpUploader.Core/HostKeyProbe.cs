using Renci.SshNet;
using Renci.SshNet.Common;

namespace MiresSftpUploader.Core;

/// <summary>The host key a server presented. <see cref="Sha256"/> is base64 without padding or prefix, as the ssh command prints it.</summary>
public sealed record PresentedHostKey(string KeyName, string Sha256, string Md5)
{
    /// <summary>The form to store as the Host Key Fingerprint.</summary>
    public string Fingerprint => "SHA256:" + Sha256;
}

/// <summary>Reads the host key a server presents, without sending any credential.</summary>
public static class HostKeyProbe
{
    public static Task<RemoteResult<PresentedHostKey>> ProbeAsync(SftpConfig sftp, CancellationToken cancellationToken) =>
        ProbeAsync(sftp.Host!, sftp.Port, TimeSpan.FromSeconds(sftp.ConnectTimeoutSeconds), cancellationToken);

    /// <summary>
    /// Starts the key exchange and refuses the key, so the connection ends before authentication: nothing secret reaches
    /// a server that has not been verified yet.
    /// </summary>
    public static async Task<RemoteResult<PresentedHostKey>> ProbeAsync(string host, int port, TimeSpan timeout, CancellationToken cancellationToken)
    {
        PresentedHostKey? presented = null;
        using var client = new SshClient(new ConnectionInfo(host, port, "probe", new NoneAuthenticationMethod("probe")) { Timeout = timeout });
        client.HostKeyReceived += (_, e) =>
        {
            presented = new PresentedHostKey(e.HostKeyName, e.FingerPrintSHA256, e.FingerPrintMD5);
            e.CanTrust = false;
        };

        try
        {
            await client.ConnectAsync(cancellationToken);
        }
        catch (OperationCanceledException)
        {
            throw;
        }
        catch (Exception ex) when (ex is SshException or IOException or System.Net.Sockets.SocketException or TimeoutException or InvalidOperationException)
        {
            if (presented is null) return RemoteResult<PresentedHostKey>.Failed($"Cannot connect to {host}:{port}: {ex.Message}");
        }

        return presented is null
            ? RemoteResult<PresentedHostKey>.Failed($"{host}:{port} did not present a host key.")
            : RemoteResult<PresentedHostKey>.Ok(presented);
    }
}

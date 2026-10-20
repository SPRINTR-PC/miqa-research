using DotNet.Testcontainers.Builders;
using DotNet.Testcontainers.Containers;
using MiresSftpUploader.Core;

namespace MiresSftpUploader.Test.Integration;

/// <summary>Where to reach the throwaway OpenSSH container and how to identify it.</summary>
public sealed record SftpServerInfo(
    string Host,
    int Port,
    string Username,
    string Password,
    string Sha256Fingerprint,
    string Md5Fingerprint,
    string EncryptedKeyPath,
    string KeyPassphrase,
    string UploadDirectory)
{
    public SftpConnection Connection(string? fingerprint = null) => new()
    {
        Host = Host,
        Port = Port,
        Username = Username,
        AuthMethod = AuthMethod.Password,
        Password = Password,
        HostKeyFingerprint = fingerprint ?? "SHA256:" + Sha256Fingerprint,
        ConnectTimeout = TimeSpan.FromSeconds(30),
    };
}

/// <summary>
/// One OpenSSH SFTP server (pinned image) shared by every container test in the run.
/// Tests that cannot reach Docker end Inconclusive.
/// </summary>
public static class SftpServer
{
    // atmoz/sftp:alpine, pinned by digest so a moving tag cannot change what the tests prove.
    private const string Image = "atmoz/sftp@sha256:7e439fabeae536fa254340724c042e11999924d906417dbb5c73602ad518813f";
    public const string KeyPassphrase = "correct horse battery";

    private static readonly Lazy<Task<SftpServerInfo>> Started = new(StartAsync);
    private static IContainer? _container;

    public static SftpServerInfo Get()
    {
        try
        {
            return Started.Value.GetAwaiter().GetResult();
        }
        catch (Exception ex) when (ex is DockerUnavailableException or ArgumentException or HttpRequestException or TimeoutException
            || ex.GetType().Name.Contains("Docker", StringComparison.OrdinalIgnoreCase))
        {
            Assert.Inconclusive("Docker is not reachable: " + ex.Message);
            throw;
        }
    }

    public static async Task StopAsync()
    {
        if (_container is not null) await _container.DisposeAsync();
    }

    private static async Task<SftpServerInfo> StartAsync()
    {
        var keyDirectory = Path.Combine(AppContext.BaseDirectory, "Fixtures");
        var container = new ContainerBuilder(Image)
            .WithPortBinding(22, assignRandomHostPort: true)
            .WithCommand("test:secret:::upload")
            .WithResourceMapping(new FileInfo(Path.Combine(keyDirectory, "test_ed25519.pub")), "/home/test/.ssh/keys/")
            .WithWaitStrategy(Wait.ForUnixContainer().UntilMessageIsLogged("Server listening on"))
            .Build();
        try
        {
            await container.StartAsync();
        }
        catch (Exception ex) when (ex is not DockerUnavailableException && IsDockerProblem(ex))
        {
            throw new DockerUnavailableException(ex.Message);
        }
        _container = container;

        var sha = await FingerprintAsync(container, "");
        var md5 = await FingerprintAsync(container, "-E md5 ");
        return new SftpServerInfo(
            container.Hostname,
            container.GetMappedPublicPort(22),
            "test",
            "secret",
            sha,
            md5,
            Path.Combine(keyDirectory, "test_ed25519"),
            KeyPassphrase,
            "/upload");
    }

    private static bool IsDockerProblem(Exception ex) =>
        ex is DockerUnavailableException || ex.GetType().Name.Contains("Docker", StringComparison.OrdinalIgnoreCase)
        || ex.Message.Contains("docker", StringComparison.OrdinalIgnoreCase);

    /// <summary>The fingerprint exactly as <c>ssh-keygen -l</c> prints it, minus its <c>SHA256:</c> / <c>MD5:</c> prefix.</summary>
    private static async Task<string> FingerprintAsync(IContainer container, string flags)
    {
        var result = await container.ExecAsync(["sh", "-c", $"ssh-keygen -l {flags}-f /etc/ssh/ssh_host_ed25519_key.pub"]);
        var token = result.Stdout.Split(' ', StringSplitOptions.RemoveEmptyEntries)[1];
        return token[(token.IndexOf(':') + 1)..];
    }
}

public sealed class DockerUnavailableException(string message) : Exception(message);

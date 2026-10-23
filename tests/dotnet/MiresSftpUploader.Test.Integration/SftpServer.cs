using DotNet.Testcontainers.Builders;
using DotNet.Testcontainers.Configurations;
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

    /// <summary>
    /// A write-only account (spike result for release-checklist item 8): its <c>/inbox</c> has mode 0300, so it can create objects in it
    /// but not list it, and sftp-server runs with umask 0377, so every object it creates is read-only and cannot be written again.
    /// Not refused: rename or delete of its own objects (the directory is its own), which is why this account cannot show a refused
    /// rename over an existing file; <see cref="StickyUser"/> does.
    /// </summary>
    public const string WriteOnlyUser = "drop";

    /// <summary>
    /// Like <see cref="WriteOnlyUser"/>, but its <c>/inbox</c> belongs to root with mode 1733 (sticky): the account cannot rename over
    /// or delete an object somebody else owns, which the server answers with permission denied. Tests seed such objects with <see cref="SeedForeignFileAsync"/>.
    /// </summary>
    public const string StickyUser = "sticky";

    /// <summary>Creates an object owned by root in the user's <c>/inbox</c>, as an earlier delivery the account cannot replace.</summary>
    public static async Task SeedForeignFileAsync(string name, string content, string user = StickyUser) =>
        await _container!.ExecAsync(["sh", "-c", $"printf %s '{content}' > /home/{user}/inbox/{name} && chmod 0444 /home/{user}/inbox/{name}"]);

    /// <summary>The write-only account on the shared server; its only writable place is <c>/inbox</c>.</summary>
    public static SftpConnection WriteOnlyConnection(string user = WriteOnlyUser) => Get().Connection() with { Username = user };

    private const string ChrootHome = "/home/test";

    /// <summary>Lists the files of a write-only user's <c>/inbox</c> as the server holds them (read as root, not through SFTP).</summary>
    public static async Task<IReadOnlyList<string>> InboxFilesAsync(string user = WriteOnlyUser)
    {
        var home = "/home/" + user;
        var result = await _container!.ExecAsync(["find", home + "/inbox", "-type", "f"]);
        return result.Stdout.Split('\n', StringSplitOptions.RemoveEmptyEntries).Select(p => p[(home.Length + "/inbox/".Length)..]).Order().ToList();
    }

    public static async Task<string> InboxReadTextAsync(string name, string user = WriteOnlyUser)
    {
        var result = await _container!.ExecAsync(["cat", "--", "/home/" + user + "/inbox/" + name]);
        if (result.ExitCode != 0) throw new InvalidOperationException(result.Stderr);
        return result.Stdout;
    }

    /// <summary>Removes every object from a write-only user's <c>/inbox</c> so tests start from an empty directory.</summary>
    public static async Task EmptyInboxAsync(string user = WriteOnlyUser) =>
        await _container!.ExecAsync(["sh", "-c", $"rm -f /home/{user}/inbox/* /home/{user}/inbox/.[!.]*"]);

    /// <summary>SHA-256 of a file as the server's own file system holds it (read by <c>sha256sum</c> inside the container, not through SFTP).</summary>
    public static async Task<string> RemoteSha256Async(string sftpPath)
    {
        var result = await _container!.ExecAsync(["sha256sum", "--", ChrootHome + sftpPath]);
        if (result.ExitCode != 0) throw new InvalidOperationException(result.Stderr);
        return result.Stdout.Split(' ')[0];
    }

    public static async Task<string> RemoteReadTextAsync(string sftpPath)
    {
        var result = await _container!.ExecAsync(["cat", "--", ChrootHome + sftpPath]);
        if (result.ExitCode != 0) throw new InvalidOperationException(result.Stderr);
        return result.Stdout;
    }

    /// <summary>Lists the files below an SFTP directory as the server holds them, recursively.</summary>
    public static async Task<IReadOnlyList<string>> RemoteFilesAsync(string sftpDirectory)
    {
        var result = await _container!.ExecAsync(["find", ChrootHome + sftpDirectory, "-type", "f"]);
        return result.Stdout.Split('\n', StringSplitOptions.RemoveEmptyEntries).Select(p => p[ChrootHome.Length..]).ToList();
    }

    private static async Task<SftpServerInfo> StartAsync()
    {
        var keyDirectory = Path.Combine(AppContext.BaseDirectory, "Fixtures");
        var container = new ContainerBuilder(Image)
            .WithPortBinding(22, assignRandomHostPort: true)
            .WithCommand("test:secret:::upload", WriteOnlyUser + ":secret:::inbox", StickyUser + ":secret:::inbox")
            .WithResourceMapping(new FileInfo(Path.Combine(keyDirectory, "test_ed25519.pub")), "/home/test/.ssh/keys/")
            // The host key mismatch tests hang up before authenticating, which OpenSSH's per-source penalties
            // answer by dropping every later connection from the same address. Switch them off for the test server,
            // and lift MaxStartups, which an emulated (slow) sshd would otherwise hit when connections pile up.
            .WithResourceMapping(
                System.Text.Encoding.ASCII.GetBytes("#!/bin/sh\nprintf 'PerSourcePenalties no\\nMaxStartups 200\\n' >> /etc/ssh/sshd_config\n"),
                "/etc/sftp.d/10-no-penalties.sh", fileMode: UnixFileModes.UserRead | UnixFileModes.UserWrite | UnixFileModes.UserExecute | UnixFileModes.GroupRead | UnixFileModes.GroupExecute | UnixFileModes.OtherRead | UnixFileModes.OtherExecute)
            // The write-only accounts: /inbox is mode 0300 and their sftp-server runs with umask 0377 (see WriteOnlyUser). Match blocks
            // come first because sshd takes the first value it finds, and the stock ForceCommand is global.
            .WithResourceMapping(
                System.Text.Encoding.ASCII.GetBytes("#!/bin/sh\nset -e\nchmod 0300 /home/drop/inbox\nchown root:root /home/sticky/inbox\nchmod 1733 /home/sticky/inbox\nprintf 'Match User drop\\n  ForceCommand internal-sftp -u 0377\\nMatch User sticky\\n  ForceCommand internal-sftp -u 0377\\nMatch All\\n' | cat - /etc/ssh/sshd_config > /tmp/sshd_config.new\ncat /tmp/sshd_config.new > /etc/ssh/sshd_config\n"),
                "/etc/sftp.d/20-write-only.sh", fileMode: UnixFileModes.UserRead | UnixFileModes.UserWrite | UnixFileModes.UserExecute | UnixFileModes.GroupRead | UnixFileModes.GroupExecute | UnixFileModes.OtherRead | UnixFileModes.OtherExecute)
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

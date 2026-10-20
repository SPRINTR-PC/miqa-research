using MiresSftpUploader.Core;

namespace MiresSftpUploader.Test.Integration;

[TestClass]
[TestCategory("Container")]
public sealed class SftpConnectionTests
{
    private static async Task<RemoteResult<IRemoteSession>> Connect(SftpConnection connection)
    {
        var result = await new SshNetRemote(connection).ConnectAsync(CancellationToken.None);
        if (result.Value is { } session) await session.DisposeAsync();
        return result;
    }

    [TestMethod]
    public async Task Host_key_mismatch_refuses_the_connection()
    {
        var server = SftpServer.Get();
        var wrong = "SHA256:" + new string('A', 43);

        var result = await Connect(server.Connection(wrong));

        Assert.AreEqual(RemoteResultKind.Failed, result.Kind);
        StringAssert.Contains(result.Reason, "Host key mismatch");
        StringAssert.Contains(result.Reason, server.Sha256Fingerprint);
    }

    [TestMethod]
    public async Task Host_key_mismatch_never_sends_the_password()
    {
        var server = SftpServer.Get();
        var wrongPassword = server.Connection("SHA256:" + new string('A', 43)) with { Password = "not-the-password" };

        var result = await Connect(wrongPassword);

        // A wrong password would be reported as an authentication failure; the host key check comes first.
        Assert.AreEqual(RemoteResultKind.Failed, result.Kind);
    }

    [TestMethod]
    [DataRow("sha256-prefixed")]
    [DataRow("sha256-bare")]
    [DataRow("md5-prefixed")]
    [DataRow("md5-bare")]
    public async Task Normalised_fingerprint_forms_connect(string form)
    {
        var server = SftpServer.Get();
        var fingerprint = form switch
        {
            "sha256-prefixed" => "SHA256:" + server.Sha256Fingerprint,
            "sha256-bare" => server.Sha256Fingerprint,
            "md5-prefixed" => "MD5:" + server.Md5Fingerprint,
            _ => server.Md5Fingerprint,
        };

        var result = await Connect(server.Connection(fingerprint));

        Assert.IsTrue(result.IsOk, result.Reason);
    }

    [TestMethod]
    public async Task Wrong_password_is_denied()
    {
        var server = SftpServer.Get();

        var result = await Connect(server.Connection() with { Password = "wrong" });

        Assert.AreEqual(RemoteResultKind.Denied, result.Kind);
    }

    [TestMethod]
    public async Task Encrypted_ed25519_private_key_with_passphrase_authenticates()
    {
        var server = SftpServer.Get();
        var connection = server.Connection() with
        {
            AuthMethod = AuthMethod.PrivateKey,
            Password = null,
            PrivateKeyPath = server.EncryptedKeyPath,
            PrivateKeyPassphrase = server.KeyPassphrase,
        };

        var result = await Connect(connection);

        Assert.IsTrue(result.IsOk, result.Reason);
    }

    [TestMethod]
    public async Task Encrypted_private_key_with_wrong_passphrase_fails_without_throwing()
    {
        var server = SftpServer.Get();
        var connection = server.Connection() with
        {
            AuthMethod = AuthMethod.PrivateKey,
            PrivateKeyPath = server.EncryptedKeyPath,
            PrivateKeyPassphrase = "wrong",
        };

        var result = await Connect(connection);

        Assert.IsFalse(result.IsOk);
    }

    private static int CheckConnection(SftpServerInfo server, string fingerprint, out string stderr)
    {
        var dir = Directory.CreateTempSubdirectory("mires-check-").FullName;
        try
        {
            var machine = Path.Combine(dir, "appsettings.json");
            File.WriteAllText(machine, System.Text.Json.JsonSerializer.Serialize(new
            {
                Sftp = new { Host = server.Host, Port = server.Port, Username = server.Username, HostKeyFingerprint = fingerprint, RemoteRoot = "/upload" },
                Sources = new[] { new { Name = "alpha", Type = "Directory", Path = dir } },
            }));
            var locations = new ConfigurationLocations(machine, Path.Combine(dir, "user.json"),
                new Dictionary<string, string?> { ["MIRES_SFTP_PASSWORD"] = server.Password });
            var err = new StringWriter();
            Cli.TryRun(["--validate-config", "--check-connection"], "1.0.0", new StringWriter(), err, out var exitCode, locations);
            stderr = err.ToString();
            return exitCode;
        }
        finally
        {
            Directory.Delete(dir, recursive: true);
        }
    }

    [TestMethod]
    public void Check_connection_with_the_right_fingerprint_exits_0()
    {
        var server = SftpServer.Get();

        Assert.AreEqual(0, CheckConnection(server, "SHA256:" + server.Sha256Fingerprint, out var err), err);
    }

    [TestMethod]
    public void Check_connection_with_a_wrong_fingerprint_exits_3()
    {
        var server = SftpServer.Get();

        Assert.AreEqual(3, CheckConnection(server, "SHA256:" + new string('A', 43), out var err));
        StringAssert.Contains(err, "Host key mismatch");
    }
}

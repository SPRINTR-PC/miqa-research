using MiresSftpUploader.Core;
using MiresSftpUploader.Test.Support;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class CheckConnectionTests : ConfigurationTestBase
{
    private (int ExitCode, string Out, string Err, SftpConnection? Used) Invoke(
        IRemote remote, Dictionary<string, string?>? env = null, params string[] extraArgs)
    {
        File.WriteAllText(MachinePath, ValidMachine().ToJsonString());
        var locations = new ConfigurationLocations(MachinePath, UserPath,
            env ?? new Dictionary<string, string?> { ["MIRES_SFTP_PASSWORD"] = "pw" });
        var stdout = new StringWriter();
        var stderr = new StringWriter();
        SftpConnection? used = null;
        Cli.TryRun(["--validate-config", "--check-connection", .. extraArgs], "1.2.3", stdout, stderr, out var exitCode, locations,
            connection => { used = connection; return remote; });
        return (exitCode, stdout.ToString(), stderr.ToString(), used);
    }

    [TestMethod]
    public void Reachable_server_exits_0_with_one_line_on_stdout()
    {
        var r = Invoke(new FakeRemote());

        Assert.AreEqual(0, r.ExitCode, r.Err);
        Assert.AreEqual(1, r.Out.Trim().Split('\n').Length);
        StringAssert.Contains(r.Out, "sftp.example.org");
        Assert.AreEqual("", r.Err);
    }

    [TestMethod]
    public void The_connection_uses_the_configured_server_pinned_fingerprint_and_the_password_secret()
    {
        var r = Invoke(new FakeRemote());

        Assert.IsNotNull(r.Used);
        Assert.AreEqual("sftp.example.org", r.Used.Host);
        Assert.AreEqual(22, r.Used.Port);
        Assert.AreEqual("u", r.Used.Username);
        Assert.AreEqual("abc", r.Used.HostKeyFingerprint);
        Assert.AreEqual("pw", r.Used.Password);
    }

    [TestMethod]
    public void Connect_failure_such_as_a_host_key_mismatch_exits_3_and_says_why_on_stderr()
    {
        var remote = new FakeRemote();
        remote.Inject(RemoteOperation.Connect, RemoteResult.Failed("Host key mismatch: presented SHA256:zzz"));

        var r = Invoke(remote);

        Assert.AreEqual(3, r.ExitCode);
        Assert.AreEqual("", r.Out);
        StringAssert.Contains(r.Err, "Host key mismatch");
    }

    [TestMethod]
    public void Refused_credentials_exit_3()
    {
        var remote = new FakeRemote();
        remote.Inject(RemoteOperation.Connect, RemoteResult.Denied("Authentication failed"));

        Assert.AreEqual(3, Invoke(remote).ExitCode);
    }

    [TestMethod]
    public void A_missing_password_secret_is_a_configuration_error_not_a_connection_attempt()
    {
        var remote = new FakeRemote();

        var r = Invoke(remote, new Dictionary<string, string?>());

        Assert.AreEqual(2, r.ExitCode);
        Assert.AreEqual(0, remote.ConnectCount);
        StringAssert.Contains(r.Err, "MIRES_SFTP_PASSWORD");
    }

    [TestMethod]
    public void An_invalid_configuration_exits_2_without_connecting()
    {
        var remote = new FakeRemote();
        File.WriteAllText(MachinePath, "{}");
        var stderr = new StringWriter();

        Cli.TryRun(["--validate-config", "--check-connection"], "1.2.3", new StringWriter(), stderr, out var exitCode,
            new ConfigurationLocations(MachinePath, UserPath, new Dictionary<string, string?>()), _ => remote);

        Assert.AreEqual(2, exitCode);
        Assert.AreEqual(0, remote.ConnectCount);
    }

    [TestMethod]
    public void Validate_config_without_check_connection_never_connects()
    {
        var remote = new FakeRemote();
        File.WriteAllText(MachinePath, ValidMachine().ToJsonString());

        Cli.TryRun(["--validate-config"], "1.2.3", new StringWriter(), new StringWriter(), out var exitCode,
            new ConfigurationLocations(MachinePath, UserPath, new Dictionary<string, string?>()), _ => remote);

        Assert.AreEqual(0, exitCode);
        Assert.AreEqual(0, remote.ConnectCount);
    }

    [TestMethod]
    public void Private_key_authentication_passes_the_key_path_and_passphrase_secret()
    {
        var machine = ValidMachine();
        machine["Sftp"]!["AuthMethod"] = "PrivateKey";
        machine["Sftp"]!["PrivateKeyPath"] = "/keys/id_ed25519";
        File.WriteAllText(MachinePath, machine.ToJsonString());
        SftpConnection? used = null;

        Cli.TryRun(["--validate-config", "--check-connection"], "1.2.3", new StringWriter(), new StringWriter(), out var exitCode,
            new ConfigurationLocations(MachinePath, UserPath, new Dictionary<string, string?> { ["MIRES_SFTP_KEY_PASSPHRASE"] = "pass" }),
            c => { used = c; return new FakeRemote(); });

        Assert.AreEqual(0, exitCode);
        Assert.AreEqual(AuthMethod.PrivateKey, used!.AuthMethod);
        Assert.AreEqual("/keys/id_ed25519", used.PrivateKeyPath);
        Assert.AreEqual("pass", used.PrivateKeyPassphrase);
    }
}

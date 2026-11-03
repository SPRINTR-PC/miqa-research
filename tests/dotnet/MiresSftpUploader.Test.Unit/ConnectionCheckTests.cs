using MiresSftpUploader.Core;
using MiresSftpUploader.Test.Support;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class ConnectionCheckTests : ConfigurationTestBase
{
    private Configuration Saved(Dictionary<string, string?>? env = null)
    {
        File.WriteAllText(MachinePath, ValidMachine().ToJsonString());
        return new Configuration(new ConfigurationLocations(MachinePath, UserPath, env ?? new Dictionary<string, string?> { ["MIRES_SFTP_PASSWORD"] = "pw" }));
    }

    [TestMethod]
    public async Task Reachable_server_is_connected_and_one_session_is_opened()
    {
        var remote = new FakeRemote();

        var result = await ConnectionCheck.CheckSavedAsync(Saved(), _ => remote, CancellationToken.None);

        Assert.AreEqual(ConnectionCheckOutcome.Connected, result.Outcome);
        Assert.AreEqual(ExitCodes.Ok, result.ExitCode);
        StringAssert.Contains(result.Message, "sftp.example.org");
        Assert.AreEqual(1, remote.ConnectCount);
    }

    [TestMethod]
    public async Task Host_key_mismatch_fails_with_the_reason()
    {
        var remote = new FakeRemote();
        remote.Inject(RemoteOperation.Connect, RemoteResult.Failed("Host key mismatch: presented SHA256:zzz"));

        var result = await ConnectionCheck.CheckSavedAsync(Saved(), _ => remote, CancellationToken.None);

        Assert.AreEqual(ConnectionCheckOutcome.Failed, result.Outcome);
        Assert.AreEqual(ExitCodes.ConnectFailed, result.ExitCode);
        StringAssert.Contains(result.Message, "Host key mismatch");
    }

    [TestMethod]
    public async Task Refused_credentials_fail()
    {
        var remote = new FakeRemote();
        remote.Inject(RemoteOperation.Connect, RemoteResult.Denied("Authentication failed"));

        var result = await ConnectionCheck.CheckSavedAsync(Saved(), _ => remote, CancellationToken.None);

        Assert.AreEqual(ConnectionCheckOutcome.Failed, result.Outcome);
        StringAssert.Contains(result.Message, "Authentication failed");
    }

    [TestMethod]
    public async Task Missing_password_is_reported_without_connecting()
    {
        var remote = new FakeRemote();

        var result = await ConnectionCheck.CheckSavedAsync(Saved(new Dictionary<string, string?>()), _ => remote, CancellationToken.None);

        Assert.AreEqual(ConnectionCheckOutcome.MissingCredentials, result.Outcome);
        Assert.AreEqual(ExitCodes.ConfigurationError, result.ExitCode);
        StringAssert.Contains(result.Message, "MIRES_SFTP_PASSWORD");
        Assert.AreEqual(0, remote.ConnectCount);
    }

    [TestMethod]
    public async Task Invalid_saved_configuration_is_reported_without_connecting()
    {
        var remote = new FakeRemote();
        File.WriteAllText(MachinePath, "{}");
        var configuration = new Configuration(new ConfigurationLocations(MachinePath, UserPath, new Dictionary<string, string?>()));

        var result = await ConnectionCheck.CheckSavedAsync(configuration, _ => remote, CancellationToken.None);

        Assert.AreEqual(ConnectionCheckOutcome.InvalidConfiguration, result.Outcome);
        Assert.AreEqual(ExitCodes.ConfigurationError, result.ExitCode);
        Assert.AreEqual(0, remote.ConnectCount);
    }

    [TestMethod]
    public async Task The_failure_reason_never_shows_a_Secret()
    {
        var remote = new FakeRemote();
        remote.Inject(RemoteOperation.Connect, RemoteResult.Failed("server said: bad login with hunter2-secret"));
        var configuration = Saved(new Dictionary<string, string?> { ["MIRES_SFTP_PASSWORD"] = "hunter2-secret" });

        var result = await ConnectionCheck.CheckSavedAsync(configuration, _ => remote, CancellationToken.None);

        Assert.AreEqual(ConnectionCheckOutcome.Failed, result.Outcome);
        Assert.DoesNotContain("hunter2-secret", result.Message);
        StringAssert.Contains(result.Message, Redactor.Mask);
    }

    [TestMethod]
    public async Task Command_line_options_are_applied_to_the_saved_configuration()
    {
        var remote = new FakeRemote();
        var options = new CliOptions { ConfigOverrides = new Dictionary<string, string> { ["Sftp:Host"] = "override.example.org" } };

        var result = await ConnectionCheck.CheckSavedAsync(Saved(), _ => remote, CancellationToken.None, options);

        StringAssert.Contains(result.Message, "override.example.org");
    }

    [TestMethod]
    public async Task An_unreadable_stored_password_is_reported_as_unreadable_not_as_not_set()
    {
        File.WriteAllText(MachinePath, ValidMachine().ToJsonString());
        var store = Path.Combine(Dir, "user", "secrets.db");
        using (var s = SecretStore.Open(store, new Identity("machine-1")))
            s.Set("sftp-password", "from-store");
        var configuration = new Configuration(new ConfigurationLocations(MachinePath, UserPath, new Dictionary<string, string?>(), store, new Identity("another-machine")));
        var remote = new FakeRemote();

        var result = await ConnectionCheck.CheckSavedAsync(configuration, _ => remote, CancellationToken.None);

        Assert.AreEqual(ConnectionCheckOutcome.MissingCredentials, result.Outcome);
        StringAssert.Contains(result.Message, "unreadable");
        StringAssert.Contains(result.Message, "--set-secret sftp-password");
        Assert.AreEqual(0, remote.ConnectCount);
    }

    [TestMethod]
    public async Task A_missing_password_is_still_reported_as_not_set()
    {
        var result = await ConnectionCheck.CheckSavedAsync(Saved(new Dictionary<string, string?>()), _ => new FakeRemote(), CancellationToken.None);

        StringAssert.Contains(result.Message, "is not set");
        Assert.DoesNotContain("unreadable", result.Message);
    }

    private sealed record Identity(string? MachineId, string Account = "alice") : IMachineIdentity;
}

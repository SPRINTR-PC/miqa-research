using MiresSftpUploader.Core;
using MiresSftpUploader.Test.Support;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class ConnectionCheckPinningTests
{
    private static readonly PresentedHostKey Key = new("ssh-ed25519", "abc123", "aa:bb");
    private static readonly Secrets WithPassword = new Configuration(new ConfigurationLocations("", "", new Dictionary<string, string?> { ["MIRES_SFTP_PASSWORD"] = "pw" })).LoadSecrets();

    private static SftpConfig Sftp(string? fingerprint) => new() { Host = "h", Username = "u", HostKeyFingerprint = fingerprint };

    private static Task<RemoteResult<PresentedHostKey>> Presents(SftpConfig _, CancellationToken __) => Task.FromResult(RemoteResult<PresentedHostKey>.Ok(Key));

    [TestMethod]
    public async Task A_pinned_fingerprint_skips_the_probe_and_the_question()
    {
        var remote = new FakeRemote();
        var probed = false;

        var result = await ConnectionCheck.RunPinningAsync(Sftp("abc"), WithPassword, _ => remote,
            (s, c) => { probed = true; return Presents(s, c); }, _ => throw new AssertFailedException("asked"), _ => throw new AssertFailedException("pinned"), CancellationToken.None);

        Assert.IsTrue(result.IsConnected);
        Assert.IsFalse(probed);
    }

    [TestMethod]
    public async Task Accepting_the_presented_key_pins_it_and_connects()
    {
        var remote = new FakeRemote();
        string? pinned = null;
        SftpConnection? used = null;

        var result = await ConnectionCheck.RunPinningAsync(Sftp(null), WithPassword, c => { used = c; return remote; },
            Presents, _ => Task.FromResult(true), fp => pinned = fp, CancellationToken.None);

        Assert.IsTrue(result.IsConnected);
        Assert.AreEqual("SHA256:abc123", pinned);
        Assert.AreEqual("abc123", used!.HostKeyFingerprint);
        StringAssert.Contains(result.Message, "SHA256:abc123");
    }

    [TestMethod]
    public async Task Declining_the_key_pins_nothing_and_never_connects()
    {
        var remote = new FakeRemote();
        string? pinned = null;

        var result = await ConnectionCheck.RunPinningAsync(Sftp("  "), WithPassword, _ => remote,
            Presents, _ => Task.FromResult(false), fp => pinned = fp, CancellationToken.None);

        Assert.AreEqual(ConnectionCheckOutcome.HostKeyNotTrusted, result.Outcome);
        Assert.IsNull(pinned);
        Assert.AreEqual(0, remote.ConnectCount);
    }

    [TestMethod]
    public async Task An_unreachable_server_is_reported_without_asking()
    {
        var result = await ConnectionCheck.RunPinningAsync(Sftp(null), WithPassword, _ => new FakeRemote(),
            (_, _) => Task.FromResult(RemoteResult<PresentedHostKey>.Failed("refused")), _ => throw new AssertFailedException("asked"), _ => { }, CancellationToken.None);

        Assert.AreEqual(ConnectionCheckOutcome.Failed, result.Outcome);
        StringAssert.Contains(result.Message, "refused");
    }

    [TestMethod]
    public async Task A_missing_host_is_an_invalid_configuration()
    {
        var result = await ConnectionCheck.RunPinningAsync(Sftp(null) with { Host = "" }, WithPassword, _ => new FakeRemote(),
            Presents, _ => Task.FromResult(true), _ => { }, CancellationToken.None);

        Assert.AreEqual(ConnectionCheckOutcome.InvalidConfiguration, result.Outcome);
    }
}

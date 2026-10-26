using Microsoft.Extensions.Logging.Abstractions;
using MiresSftpUploader.Core;
using MiresSftpUploader.Test.Support;

namespace MiresSftpUploader.Test.Integration;

/// <summary>Verification against the real OpenSSH server, an SFTP-only account (no command channel).</summary>
[TestClass]
[TestCategory("Container")]
public sealed class SftpVerificationTests
{
    private static Engine NewEngine(VerificationLevel level, string root, params ISource[] sources) =>
        new(new SshNetRemote(SftpServer.Get().Connection()), sources,
            new EngineSettings
            {
                RemoteRoot = root,
                Retry = new RetrySettings { MaxAttempts = 1, BaseDelay = TimeSpan.Zero, MaxDelay = TimeSpan.Zero },
                Verification = new VerificationSettings { AfterUpload = level },
            },
            NullLogger<Engine>.Instance, TimeProvider.System);

    [TestMethod]
    public async Task Hash_is_unavailable_on_an_SFTP_only_account_and_the_Run_exits_2_without_uploading()
    {
        var root = SftpServer.Get().UploadDirectory + "/verify-hash-" + Guid.NewGuid().ToString("N");
        var source = new FakeSource("scans").Add("a.txt", "alpha");

        var result = await NewEngine(VerificationLevel.Hash, root, source).RunAsync(new RunOptions(), new Progress<RunEvent>(), CancellationToken.None);

        Assert.AreEqual(ExitCodes.ConfigurationError, result.ExitCode, result.Reason);
        Assert.IsEmpty(await SftpServer.RemoteFilesAsync(root));
    }

    [TestMethod]
    [DataRow(VerificationLevel.Size)]
    [DataRow(VerificationLevel.ReadBack)]
    public async Task Size_and_ReadBack_verify_the_part_file_over_SFTP(VerificationLevel level)
    {
        var root = SftpServer.Get().UploadDirectory + "/verify-" + level + "-" + Guid.NewGuid().ToString("N");
        var source = new FakeSource("scans").Add("a.txt", "alpha");

        var result = await NewEngine(level, root, source).RunAsync(new RunOptions(), new Progress<RunEvent>(), CancellationToken.None);

        Assert.AreEqual(ExitCodes.Ok, result.ExitCode, result.Reason);
        Assert.AreEqual(1, result.Verified);
        Assert.AreEqual("alpha", await SftpServer.RemoteReadTextAsync(root + "/scans/a.txt"));
    }
}

using System.Security.Cryptography;
using System.Text.Json;
using Microsoft.Extensions.Logging.Abstractions;
using MiresSftpUploader.Core;
using MiresSftpUploader.Test.Support;

namespace MiresSftpUploader.Test.Integration;

/// <summary>
/// Write-only Access against the real OpenSSH server. The accounts are described at <see cref="SftpServer.WriteOnlyUser"/>:
/// an <c>/inbox</c> of mode 0300 that cannot be listed, with objects that cannot be written a second time.
/// </summary>
[TestClass]
[TestCategory("Container")]
[DoNotParallelize] // the tests share the accounts' /inbox directories
public sealed class SftpWriteOnlyTests
{
    private string _dir = "";

    [TestInitialize]
    public async Task Setup()
    {
        _dir = Directory.CreateTempSubdirectory("mires-wo-").FullName;
        SftpServer.Get();
        await SftpServer.EmptyInboxAsync();
        await SftpServer.EmptyInboxAsync(SftpServer.StickyUser);
    }

    [TestCleanup]
    public void Cleanup()
    {
        try { Directory.Delete(_dir, recursive: true); } catch (IOException) { }
    }

    private EngineSettings Settings(UploadStrategy strategy) => new()
    {
        RemoteRoot = "/inbox",
        Destination = "container:" + strategy,
        RemoteAccess = RemoteAccess.Auto,
        UploadStrategy = strategy,
        Retry = new RetrySettings { MaxAttempts = 1, BaseDelay = TimeSpan.Zero, MaxDelay = TimeSpan.Zero },
        State = new StateSettings { Path = Path.Combine(_dir, "state.db") },
    };

    private sealed class Outcomes : IProgress<RunEvent>
    {
        private readonly Dictionary<string, FileOutcomeChanged> _last = new();
        public void Report(RunEvent value)
        {
            if (value is FileOutcomeChanged changed) lock (_last) _last[changed.RelativePath] = changed;
        }
        public FileOutcomeChanged Of(string path) { lock (_last) return _last[path]; }
    }

    private static async Task<(RunResult Result, Outcomes Files)> Run(string user, EngineSettings settings, FakeSource source)
    {
        var outcomes = new Outcomes();
        var result = await new Engine(new SshNetRemote(SftpServer.WriteOnlyConnection(user)), [source], settings, NullLogger<Engine>.Instance, TimeProvider.System)
            .RunAsync(new RunOptions(), outcomes, CancellationToken.None);
        return (result, outcomes);
    }

    private static string Sha256(string text) => Convert.ToHexStringLower(SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(text)));

    [TestMethod]
    public async Task The_write_only_account_can_stat_but_not_list_its_inbox_and_cannot_write_an_object_twice()
    {
        var remote = new SshNetRemote(SftpServer.WriteOnlyConnection());
        var connect = await remote.ConnectAsync(CancellationToken.None);
        Assert.IsTrue(connect.IsOk, connect.Reason);
        await using var session = connect.Value!;

        var list = await session.ListAsync("/inbox", CancellationToken.None);
        var first = await session.UploadAsync(new MemoryStream([1, 2, 3]), "/inbox/once.bin", CancellationToken.None);
        var second = await session.UploadAsync(new MemoryStream([4]), "/inbox/once.bin", CancellationToken.None);

        Assert.AreEqual(RemoteResultKind.Denied, list.Kind, list.Reason);
        Assert.IsTrue(first.IsOk, first.Reason);
        Assert.AreEqual(RemoteResultKind.Denied, second.Kind, second.Reason);
    }

    [TestMethod]
    public async Task Auto_detects_write_only_and_a_Direct_Run_delivers_files_and_Manifest_without_reading_or_deleting()
    {
        var settings = Settings(UploadStrategy.Direct);

        var (result, _) = await Run(SftpServer.WriteOnlyUser, settings, new FakeSource("inbox", "/inbox").Add("a.txt", "alpha"));

        Assert.AreEqual(ExitCodes.Ok, result.ExitCode, result.Reason);
        Assert.AreEqual("a.txt, manifest.json", string.Join(", ", await SftpServer.InboxFilesAsync()));
        Assert.AreEqual("alpha", await SftpServer.InboxReadTextAsync("a.txt"));
        using var manifest = JsonDocument.Parse(await SftpServer.InboxReadTextAsync("manifest.json"));
        var member = manifest.RootElement.GetProperty("members")[0];
        Assert.AreEqual(Sha256("alpha"), member.GetProperty("sha256").GetString(), "the Manifest hash is the hash of what is on the server");
        Assert.IsTrue(member.GetProperty("directUpload").GetBoolean());
    }

    [TestMethod]
    public async Task A_changed_file_is_Failed_with_RemoteDenied_and_the_next_Manifest_is_run_stamped_with_supersedes()
    {
        var settings = Settings(UploadStrategy.Direct);
        await Run(SftpServer.WriteOnlyUser, settings, new FakeSource("inbox", "/inbox").Add("a.txt", "alpha"));

        var (second, files) = await Run(SftpServer.WriteOnlyUser, settings, new FakeSource("inbox", "/inbox").Add("a.txt", "changed").Add("b.txt", "beta"));

        Assert.AreEqual(ExitCodes.SomeFilesFailed, second.ExitCode, second.Reason);
        Assert.AreEqual(FileOutcome.Failed, files.Of("a.txt").Outcome);
        StringAssert.StartsWith(files.Of("a.txt").Reason, "RemoteDenied");
        Assert.AreEqual(FileOutcome.Succeeded, files.Of("b.txt").Outcome);
        Assert.AreEqual("alpha", await SftpServer.InboxReadTextAsync("a.txt"), "the server copy is untouched");
        var stamped = $"manifest.{second.RunId}.json";
        Assert.AreEqual(string.Join(", ", new[] { "a.txt", "b.txt", "manifest.json", stamped }.Order()), string.Join(", ", await SftpServer.InboxFilesAsync()));
        using var manifest = JsonDocument.Parse(await SftpServer.InboxReadTextAsync(stamped));
        CollectionAssert.AreEqual(new[] { "manifest.json" },
            manifest.RootElement.GetProperty("run").GetProperty("supersedes").EnumerateArray().Select(e => e.GetString()).ToArray());
        Assert.IsFalse(manifest.RootElement.GetProperty("complete").GetBoolean());
        Assert.AreEqual("a.txt", manifest.RootElement.GetProperty("failures")[0].GetProperty("path").GetString());
    }

    [TestMethod]
    public async Task A_refused_rename_is_Failed_with_RemoteDenied_with_no_fallback_and_the_part_file_stays()
    {
        await SftpServer.SeedForeignFileAsync("a.txt", "alpha");
        var settings = Settings(UploadStrategy.PartThenRename);

        var (result, files) = await Run(SftpServer.StickyUser, settings, new FakeSource("inbox", "/inbox").Add("a.txt", "a newer version").Add("b.txt", "beta"));

        Assert.AreEqual(ExitCodes.SomeFilesFailed, result.ExitCode, result.Reason);
        StringAssert.StartsWith(files.Of("a.txt").Reason, "RemoteDenied");
        Assert.AreEqual(FileOutcome.Succeeded, files.Of("b.txt").Outcome, "a new name still works");
        Assert.AreEqual("alpha", await SftpServer.InboxReadTextAsync("a.txt", SftpServer.StickyUser), "no silent fallback: the earlier delivery is untouched");
        var onServer = await SftpServer.InboxFilesAsync(SftpServer.StickyUser);
        Assert.IsTrue(onServer.Contains("a.txt.part"), "stale .part files are never deleted: " + string.Join(", ", onServer));
    }
}

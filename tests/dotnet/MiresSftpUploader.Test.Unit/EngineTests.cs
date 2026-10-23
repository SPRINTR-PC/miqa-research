using System.Security.Cryptography;
using System.Text.Json;
using Microsoft.Extensions.Logging.Abstractions;
using MiresSftpUploader.Core;
using MiresSftpUploader.Test.Support;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class EngineTests
{
    private static readonly EngineSettings FastSettings = new()
    {
        RemoteRoot = "/upload",
        Retry = new RetrySettings { MaxAttempts = 3, BaseDelay = TimeSpan.Zero, MaxDelay = TimeSpan.Zero },
    };

    private static Engine NewEngine(FakeRemote remote, params ISource[] sources) =>
        new(remote, sources, FastSettings, NullLogger<Engine>.Instance, TimeProvider.System);

    private static string Sha256(byte[] data) => Convert.ToHexStringLower(SHA256.HashData(data));

    [TestMethod]
    public async Task Headless_run_uploads_every_file_and_exits_zero()
    {
        var remote = new FakeRemote();
        var source = new FakeSource("scans")
            .Add("a.txt", "alpha")
            .Add("sub/dir/b.bin", new byte[] { 1, 2, 3 });

        var result = await NewEngine(remote, source).RunAsync(new RunOptions(), new Progress<RunEvent>(), CancellationToken.None);

        Assert.AreEqual(0, result.ExitCode);
        Assert.AreEqual(2, result.Count(FileOutcome.Succeeded));
        Assert.AreEqual("alpha", remote.ReadText("/upload/scans/a.txt"));
        CollectionAssert.AreEqual(new byte[] { 1, 2, 3 }, remote.Files["/upload/scans/sub/dir/b.bin"]);
        Assert.IsFalse(remote.Files.Keys.Any(k => k.EndsWith(".part")), "no .part file may remain");
    }

    [TestMethod]
    public async Task Manifest_hash_equals_sha256_of_uploaded_content()
    {
        var remote = new FakeRemote();
        var payload = new byte[300_000];
        new Random(42).NextBytes(payload);
        var source = new FakeSource("scans").Add("big.bin", payload).Add("empty.txt", Array.Empty<byte>());

        await NewEngine(remote, source).RunAsync(new RunOptions(), new Progress<RunEvent>(), CancellationToken.None);

        using var manifest = JsonDocument.Parse(remote.ReadText("/upload/scans/manifest.json"));
        var root = manifest.RootElement;
        Assert.AreEqual(1, root.GetProperty("schemaVersion").GetInt32());
        Assert.IsTrue(root.GetProperty("complete").GetBoolean());
        var files = root.GetProperty("members").EnumerateArray().ToDictionary(
            f => f.GetProperty("path").GetString()!, f => f.GetProperty("sha256").GetString()!);
        Assert.AreEqual(Sha256(remote.Files["/upload/scans/big.bin"]), files["big.bin"]);
        Assert.AreEqual(Sha256(payload), files["big.bin"]);
        Assert.AreEqual(Sha256([]), files["empty.txt"]);
    }

    [TestMethod]
    public async Task Transient_failure_is_retried_and_file_succeeds()
    {
        var remote = new FakeRemote();
        remote.Inject(RemoteOperation.Upload, RemoteResult.Failed("connection reset"), times: 2, pathContains: "flaky.txt");
        var source = new FakeSource("scans").Add("flaky.txt", "x");

        var result = await NewEngine(remote, source).RunAsync(new RunOptions(), new Progress<RunEvent>(), CancellationToken.None);

        Assert.AreEqual(0, result.ExitCode);
        Assert.AreEqual(1, result.Count(FileOutcome.Succeeded));
        Assert.AreEqual("x", remote.ReadText("/upload/scans/flaky.txt"));
    }

    [TestMethod]
    public async Task Failing_file_does_not_abort_the_run_and_is_listed_in_the_manifest()
    {
        var remote = new FakeRemote();
        remote.Inject(RemoteOperation.Upload, RemoteResult.Failed("disk full"), times: 3, pathContains: "bad.txt");
        var source = new FakeSource("scans").Add("a.txt", "a").Add("bad.txt", "b").Add("c.txt", "c");

        var result = await NewEngine(remote, source).RunAsync(new RunOptions(), new Progress<RunEvent>(), CancellationToken.None);

        Assert.AreEqual(1, result.ExitCode);
        Assert.AreEqual(2, result.Count(FileOutcome.Succeeded));
        Assert.AreEqual(1, result.Count(FileOutcome.Failed));
        Assert.IsFalse(remote.Files.ContainsKey("/upload/scans/bad.txt"));
        using var manifest = JsonDocument.Parse(remote.ReadText("/upload/scans/manifest.json"));
        Assert.IsFalse(manifest.RootElement.GetProperty("complete").GetBoolean());
        var failure = manifest.RootElement.GetProperty("failures").EnumerateArray().Single();
        Assert.AreEqual("bad.txt", failure.GetProperty("path").GetString());
    }

    [TestMethod]
    public async Task Retries_stop_at_the_retry_limit()
    {
        var remote = new FakeRemote();
        remote.Inject(RemoteOperation.Upload, RemoteResult.Failed("nope"), times: 100, pathContains: "bad.txt");
        var source = new FakeSource("scans").Add("bad.txt", "b");
        var events = new List<RunEvent>();

        await NewEngine(remote, source).RunAsync(new RunOptions(), new SyncProgress(events), CancellationToken.None);

        var attempts = events.OfType<FileOutcomeChanged>().Count(e => e.Outcome == FileOutcome.Hashing);
        Assert.AreEqual(3, attempts);
    }

    [TestMethod]
    public async Task Denied_file_fails_without_retry_and_says_so()
    {
        var remote = new FakeRemote();
        remote.Inject(RemoteOperation.Upload, RemoteResult.Denied("permission denied"), times: 100, pathContains: "bad.txt");
        var source = new FakeSource("scans").Add("bad.txt", "b");
        var events = new List<RunEvent>();

        var result = await NewEngine(remote, source).RunAsync(new RunOptions(), new SyncProgress(events), CancellationToken.None);

        Assert.AreEqual(1, result.ExitCode);
        Assert.AreEqual(1, events.OfType<FileOutcomeChanged>().Count(e => e.Outcome == FileOutcome.Hashing));
        StringAssert.Contains(events.OfType<FileOutcomeChanged>().Last().Reason, "RemoteDenied");
    }

    [TestMethod]
    public async Task Cancelling_returns_exit_code_130()
    {
        var remote = new FakeRemote();
        var source = new FakeSource("scans").Add("a.txt", "a");
        using var cts = new CancellationTokenSource();
        await cts.CancelAsync();

        var result = await NewEngine(remote, source).RunAsync(new RunOptions(), new Progress<RunEvent>(), cts.Token);

        Assert.AreEqual(130, result.ExitCode);
    }

    [TestMethod]
    public async Task Dry_run_uploads_nothing()
    {
        var remote = new FakeRemote();
        var source = new FakeSource("scans").Add("a.txt", "a");

        var result = await NewEngine(remote, source).RunAsync(new RunOptions { DryRun = true }, new Progress<RunEvent>(), CancellationToken.None);

        Assert.AreEqual(0, result.ExitCode);
        Assert.AreEqual(0, remote.ConnectCount);
        Assert.IsEmpty(remote.Files);
    }

    [TestMethod]
    public async Task Unknown_source_is_a_configuration_error()
    {
        var result = await NewEngine(new FakeRemote(), new FakeSource("scans"))
            .RunAsync(new RunOptions { SourceNames = ["nope"] }, new Progress<RunEvent>(), CancellationToken.None);

        Assert.AreEqual(2, result.ExitCode);
    }

    [TestMethod]
    public async Task Connection_failure_is_exit_code_3()
    {
        var remote = new FakeRemote();
        remote.Inject(RemoteOperation.Connect, RemoteResult.Failed("host key mismatch"), times: 100);
        var source = new FakeSource("scans").Add("a.txt", "a");

        var result = await NewEngine(remote, source).RunAsync(new RunOptions(), new Progress<RunEvent>(), CancellationToken.None);

        Assert.AreEqual(3, result.ExitCode);
        StringAssert.Contains(result.Reason, "host key mismatch");
    }

    [TestMethod]
    public async Task Remote_path_override_is_used_for_a_source()
    {
        var remote = new FakeRemote();
        var source = new FakeSource("scans", remotePath: "/drop/custom").Add("a.txt", "a");

        await NewEngine(remote, source).RunAsync(new RunOptions(), new Progress<RunEvent>(), CancellationToken.None);

        Assert.AreEqual("a", remote.ReadText("/drop/custom/a.txt"));
        Assert.IsTrue(remote.Files.ContainsKey("/drop/custom/manifest.json"));
    }

    private sealed class SyncProgress(List<RunEvent> sink) : IProgress<RunEvent>
    {
        public void Report(RunEvent value) { lock (sink) sink.Add(value); }
    }
}

using System.Text.Json;
using Microsoft.Extensions.Logging.Abstractions;
using MiresSftpUploader.Core;
using MiresSftpUploader.Test.Support;

namespace MiresSftpUploader.Test.Unit;

/// <summary>
/// How a Run ends when it does not finish normally: the Manifest is still uploaded and says it is incomplete, the In-progress
/// Marker is removed only together with a final Manifest, a Manifest that cannot be uploaded fails the Run, and a worker that
/// cannot connect never makes the others drop files.
/// </summary>
[TestClass]
public sealed class RunFinalizationTests
{
    private const string Marker = "/upload/scans/manifest.json.inprogress";
    private const string ManifestPath = "/upload/scans/manifest.json";

    private static EngineSettings Settings(RemoteAccess access = RemoteAccess.ReadWrite, int parallel = 1) => new()
    {
        RemoteRoot = "/upload",
        RemoteAccess = access,
        MaxParallelUploads = parallel,
        Retry = new RetrySettings { MaxAttempts = 1, BaseDelay = TimeSpan.Zero, MaxDelay = TimeSpan.Zero },
    };

    private static Task<RunResult> Run(EngineSettings settings, IRemote remote, FakeSource source, CancellationToken ct = default) =>
        new Engine(remote, [source], settings, NullLogger<Engine>.Instance, TimeProvider.System)
            .RunAsync(new RunOptions(), new Progress<RunEvent>(), ct);

    private static JsonElement ManifestOf(FakeRemote remote) => JsonDocument.Parse(remote.Files[ManifestPath]).RootElement;

    private static string[] FailedPaths(JsonElement manifest) =>
        manifest.GetProperty("failures").EnumerateArray().Select(f => f.GetProperty("path").GetString()!).Order().ToArray();

    /// <summary>Lets the first connections through and refuses every later one.</summary>
    private sealed class DropsAfter(FakeRemote inner, int connections) : IRemote
    {
        private int _count;

        public Task<RemoteResult<IRemoteSession>> ConnectAsync(CancellationToken cancellationToken) =>
            Interlocked.Increment(ref _count) <= connections
                ? inner.ConnectAsync(cancellationToken)
                : Task.FromResult(RemoteResult<IRemoteSession>.Failed("connection reset"));
    }

    [TestMethod]
    public async Task A_cancelled_Run_uploads_an_incomplete_Manifest_and_removes_the_Marker()
    {
        var remote = new FakeRemote();
        using var cts = new CancellationTokenSource();
        var source = new FakeSource("scans").Add("a.txt", "a").Add("b.txt", "b");
        source.AfterOpen = _ => cts.Cancel();

        var result = await Run(Settings(), remote, source, cts.Token);

        Assert.AreEqual(ExitCodes.Cancelled, result.ExitCode);
        var manifest = ManifestOf(remote);
        Assert.IsFalse(manifest.GetProperty("complete").GetBoolean());
        CollectionAssert.AreEqual(new[] { "a.txt", "b.txt" }, FailedPaths(manifest), "files that were not delivered are listed, not left out");
        Assert.IsFalse(remote.Files.ContainsKey(Marker), "the final Manifest is there, so the Marker goes");
    }

    [TestMethod]
    public async Task A_Run_whose_workers_cannot_connect_uploads_an_incomplete_Manifest_and_exits_3()
    {
        var remote = new FakeRemote();
        remote.Inject(RemoteOperation.Connect, RemoteResult.Failed("connection refused"), times: 2);
        var source = new FakeSource("scans").Add("a.txt", "a").Add("b.txt", "b");

        var result = await Run(Settings(RemoteAccess.WriteOnly, parallel: 2), remote, source);

        Assert.AreEqual(ExitCodes.ConnectFailed, result.ExitCode);
        StringAssert.Contains(result.Reason, "connection refused");
        Assert.AreEqual(2, result.Count(FileOutcome.Failed), "files that were never attempted are reported, not left Pending");
        Assert.AreEqual(0, result.Count(FileOutcome.Pending));
        var manifest = ManifestOf(remote);
        Assert.IsFalse(manifest.GetProperty("complete").GetBoolean());
        CollectionAssert.AreEqual(new[] { "a.txt", "b.txt" }, FailedPaths(manifest));
    }

    [TestMethod]
    public async Task A_worker_that_cannot_connect_does_not_make_the_others_drop_files()
    {
        var remote = new FakeRemote();
        remote.Inject(RemoteOperation.Connect, RemoteResult.Failed("connection refused"), times: 1);
        var source = new FakeSource("scans").Add("a.txt", "a").Add("b.txt", "b").Add("c.txt", "c");

        var result = await Run(Settings(RemoteAccess.WriteOnly, parallel: 2), remote, source);

        Assert.AreEqual(ExitCodes.Ok, result.ExitCode, result.Reason);
        Assert.AreEqual(3, result.Count(FileOutcome.Succeeded));
        Assert.IsTrue(ManifestOf(remote).GetProperty("complete").GetBoolean());
    }

    [TestMethod]
    public async Task A_Manifest_that_cannot_be_uploaded_fails_the_Run_and_leaves_the_Marker()
    {
        var remote = new FakeRemote();
        remote.Inject(RemoteOperation.Upload, RemoteResult.Failed("disk full"), times: 99, pathContains: "manifest.json.part");

        var result = await Run(Settings(), remote, new FakeSource("scans").Add("a.txt", "a"));

        Assert.AreNotEqual(ExitCodes.Ok, result.ExitCode);
        StringAssert.Contains(result.Reason, "Manifest");
        StringAssert.Contains(result.Reason, "scans");
        Assert.IsTrue(remote.Files.ContainsKey(Marker), "consumers must not take a missing or stale Manifest for the final one");
        Assert.IsFalse(remote.Files.ContainsKey(ManifestPath));
    }

    [TestMethod]
    public async Task A_Run_that_cannot_reconnect_for_the_Manifest_exits_3_and_leaves_the_Marker()
    {
        var remote = new FakeRemote();

        // Connections: the Marker, the one worker, then the Manifest.
        var result = await Run(Settings(), new DropsAfter(remote, 2), new FakeSource("scans").Add("a.txt", "a"));

        Assert.AreEqual(ExitCodes.ConnectFailed, result.ExitCode);
        Assert.IsTrue(remote.Files.ContainsKey(Marker));
        Assert.IsFalse(remote.Files.ContainsKey(ManifestPath));
    }
}

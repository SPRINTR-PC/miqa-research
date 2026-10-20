using System.Security.Cryptography;
using System.Text.Json;
using Microsoft.Extensions.Logging.Abstractions;
using MiresSftpUploader.Core;
using MiresSftpUploader.Test.Support;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class ManifestTests
{
    private string _dir = "";

    [TestInitialize]
    public void Setup() => _dir = Directory.CreateTempSubdirectory("mires-manifest-").FullName;

    [TestCleanup]
    public void Cleanup()
    {
        try { Directory.Delete(_dir, recursive: true); } catch (IOException) { }
    }

    private EngineSettings Settings(bool withState = true) => new()
    {
        RemoteRoot = "/upload",
        Destination = "sftp.example:22",
        Retry = new RetrySettings { MaxAttempts = 1, BaseDelay = TimeSpan.Zero, MaxDelay = TimeSpan.Zero },
        State = new StateSettings { Path = withState ? Path.Combine(_dir, "state.db") : null },
        MachineName = "lab-pc-7",
    };

    private static Task<RunResult> Run(EngineSettings settings, FakeRemote remote, RunOptions? options, params ISource[] sources) =>
        new Engine(remote, sources, settings, NullLogger<Engine>.Instance, TimeProvider.System)
            .RunAsync(options ?? new RunOptions(), new Progress<RunEvent>(), CancellationToken.None);

    private static JsonDocument ManifestOf(FakeRemote remote, string path = "/upload/scans/manifest.json") =>
        JsonDocument.Parse(remote.Files[path]);

    private static string Sha256(string text) => Convert.ToHexStringLower(SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(text)));

    [TestMethod]
    public async Task Manifest_has_provenance_a_directory_tree_and_flat_members()
    {
        var remote = new FakeRemote();
        var source = new FakeSource("scans").Add("a.txt", "alpha").Add("sub/dir/b.txt", "beta").Add("sub/c.txt", "gamma");

        var result = await Run(Settings(), remote, null, source);

        using var doc = ManifestOf(remote);
        var root = doc.RootElement;
        Assert.AreEqual(1, root.GetProperty("schemaVersion").GetInt32());
        Assert.AreEqual("sha256", root.GetProperty("hashAlgorithm").GetString());
        Assert.AreEqual("scans", root.GetProperty("source").GetString());
        Assert.IsTrue(root.GetProperty("complete").GetBoolean());
        var run = root.GetProperty("run");
        Assert.AreEqual(result.RunId.ToString(), run.GetProperty("runId").GetString());
        Assert.AreEqual("Run", run.GetProperty("mode").GetString());
        Assert.AreEqual("lab-pc-7", run.GetProperty("machineName").GetString());
        Assert.IsTrue(run.TryGetProperty("startedAt", out _) && run.TryGetProperty("completedAt", out _) && run.TryGetProperty("toolVersion", out _));

        var members = root.GetProperty("members").EnumerateArray().ToDictionary(m => m.GetProperty("path").GetString()!);
        CollectionAssert.AreEqual(new[] { "a.txt", "sub/c.txt", "sub/dir/b.txt" }, members.Keys.Order(StringComparer.Ordinal).ToArray());
        Assert.AreEqual(Sha256("beta"), members["sub/dir/b.txt"].GetProperty("sha256").GetString());
        Assert.AreEqual(4, members["sub/dir/b.txt"].GetProperty("size").GetInt64());

        var tree = root.GetProperty("root");
        Assert.AreEqual("directory", tree.GetProperty("type").GetString());
        var top = tree.GetProperty("children").EnumerateArray().ToList();
        CollectionAssert.AreEqual(new[] { "a.txt", "sub" }, top.Select(n => n.GetProperty("name").GetString()).ToArray());
        var subChildren = top[1].GetProperty("children").EnumerateArray().ToList();
        CollectionAssert.AreEqual(new[] { "c.txt", "dir" }, subChildren.Select(n => n.GetProperty("name").GetString()).ToArray());
        var b = subChildren[1].GetProperty("children").EnumerateArray().Single();
        Assert.AreEqual("file", b.GetProperty("type").GetString());
        Assert.AreEqual(Sha256("beta"), b.GetProperty("sha256").GetString());
    }
}

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

    [TestMethod]
    public async Task Manifest_is_cumulative_and_flags_files_that_are_gone_from_the_Source()
    {
        var remote = new FakeRemote();
        var source = new FakeSource("scans").Add("a.txt", "alpha").Add("b.txt", "beta");
        await Run(Settings(), remote, null, source);
        source.Remove("a.txt").Add("c.txt", "gamma");

        await Run(Settings(), remote, null, source);

        using var doc = ManifestOf(remote);
        var members = doc.RootElement.GetProperty("members").EnumerateArray().ToDictionary(m => m.GetProperty("path").GetString()!);
        CollectionAssert.AreEqual(new[] { "a.txt", "b.txt", "c.txt" }, members.Keys.Order(StringComparer.Ordinal).ToArray());
        Assert.IsTrue(members["a.txt"].GetProperty("missingAtSource").GetBoolean());
        Assert.IsFalse(members["b.txt"].TryGetProperty("missingAtSource", out _));
        Assert.AreEqual(Sha256("alpha"), members["a.txt"].GetProperty("sha256").GetString());
        Assert.IsTrue(doc.RootElement.GetProperty("complete").GetBoolean(), "a vanished file does not make the delivery incomplete");
    }

    [TestMethod]
    public async Task A_file_whose_new_version_failed_keeps_its_earlier_hash_and_size_and_is_listed_as_a_failure()
    {
        var remote = new FakeRemote();
        var source = new FakeSource("scans").Add("a.txt", "alpha").Add("b.txt", "beta");
        await Run(Settings(), remote, null, source);
        source.Add("a.txt", "alpha, revised", new DateTimeOffset(2026, 3, 3, 0, 0, 0, TimeSpan.Zero));
        remote.Inject(RemoteOperation.Upload, RemoteResult.Failed("disk full"), pathContains: "a.txt");

        var result = await Run(Settings(), remote, null, source);

        Assert.AreEqual(1, result.ExitCode);
        using var doc = ManifestOf(remote);
        Assert.IsFalse(doc.RootElement.GetProperty("complete").GetBoolean());
        var failure = doc.RootElement.GetProperty("failures").EnumerateArray().Single();
        Assert.AreEqual("a.txt", failure.GetProperty("path").GetString());
        StringAssert.Contains(failure.GetProperty("reason").GetString(), "disk full");
        var a = doc.RootElement.GetProperty("members").EnumerateArray().Single(m => m.GetProperty("path").GetString() == "a.txt");
        Assert.AreEqual(Sha256("alpha"), a.GetProperty("sha256").GetString());
        Assert.AreEqual(5, a.GetProperty("size").GetInt64());
    }

    [TestMethod]
    public async Task A_never_delivered_failed_file_appears_only_in_failures()
    {
        var remote = new FakeRemote();
        remote.Inject(RemoteOperation.Upload, RemoteResult.Failed("disk full"), times: 3, pathContains: "bad.txt");
        var source = new FakeSource("scans").Add("good.txt", "g").Add("bad.txt", "b");

        await Run(Settings(), remote, null, source);

        using var doc = ManifestOf(remote);
        CollectionAssert.AreEqual(new[] { "good.txt" }, doc.RootElement.GetProperty("members").EnumerateArray().Select(m => m.GetProperty("path").GetString()).ToArray());
        Assert.AreEqual("bad.txt", doc.RootElement.GetProperty("failures")[0].GetProperty("path").GetString());
    }

    [TestMethod]
    public async Task A_Too_Recent_file_makes_the_Manifest_incomplete_and_is_listed_as_deferred()
    {
        var remote = new FakeRemote();
        var source = new FakeSource("scans").Add("old.txt", "o").Add("fresh.txt", "f", DateTimeOffset.UtcNow);
        var settings = Settings() with { Scan = new ScanConfig { MinFileAgeSeconds = 3600 } };

        var result = await Run(settings, remote, null, source);

        Assert.AreEqual(0, result.ExitCode);
        using var doc = ManifestOf(remote);
        Assert.IsFalse(doc.RootElement.GetProperty("complete").GetBoolean());
        Assert.AreEqual("fresh.txt", doc.RootElement.GetProperty("deferred")[0].GetProperty("path").GetString());
        Assert.AreEqual(0, doc.RootElement.GetProperty("failures").GetArrayLength());
    }

    [TestMethod]
    public async Task Manifest_tool_version_is_the_informational_version_of_the_app_and_the_engine()
    {
        var remote = new FakeRemote();
        var source = new FakeSource("scans").Add("a.txt", "alpha");

        await Run(Settings(), remote, null, source);

        static string InformationalVersion(System.Reflection.Assembly assembly) =>
            assembly.GetCustomAttributes(typeof(System.Reflection.AssemblyInformationalVersionAttribute), false)
                .Cast<System.Reflection.AssemblyInformationalVersionAttribute>().Single().InformationalVersion;
        using var doc = ManifestOf(remote);
        var tool = doc.RootElement.GetProperty("run").GetProperty("toolVersion").GetString();
        Assert.AreEqual(InformationalVersion(typeof(MiresSftpUploader.App).Assembly), tool);
        Assert.AreEqual(InformationalVersion(typeof(Engine).Assembly), tool);
    }
}

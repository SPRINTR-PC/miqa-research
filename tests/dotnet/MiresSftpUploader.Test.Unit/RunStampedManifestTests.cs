using System.Text.Json;
using Microsoft.Extensions.Logging.Abstractions;
using MiresSftpUploader.Core;
using MiresSftpUploader.Test.Support;

namespace MiresSftpUploader.Test.Unit;

/// <summary>On a server that refuses to overwrite or delete, each Run uploads its own Manifest files and names what they replace.</summary>
[TestClass]
public sealed class RunStampedManifestTests
{
    private string _dir = "";

    [TestInitialize]
    public void Setup() => _dir = Directory.CreateTempSubdirectory("mires-stamped-").FullName;

    [TestCleanup]
    public void Cleanup()
    {
        try { Directory.Delete(_dir, recursive: true); } catch (IOException) { }
    }

    private EngineSettings Settings(bool withState = true, UploadStrategy strategy = UploadStrategy.PartThenRename) => new()
    {
        RemoteRoot = "/upload",
        Destination = "sftp.example:22",
        RemoteAccess = RemoteAccess.WriteOnly,
        UploadStrategy = strategy,
        WriteFlatManifest = true,
        Retry = new RetrySettings { MaxAttempts = 2, BaseDelay = TimeSpan.Zero, MaxDelay = TimeSpan.Zero },
        State = new StateSettings { Path = withState ? Path.Combine(_dir, "state.db") : null },
    };

    private static async Task<RunResult> Run(EngineSettings settings, FakeRemote remote, FakeSource source) =>
        await new Engine(remote, [source], settings, NullLogger<Engine>.Instance, TimeProvider.System)
            .RunAsync(new RunOptions(), new Progress<RunEvent>(), CancellationToken.None);

    private static JsonDocument Manifest(FakeRemote remote, string name) => JsonDocument.Parse(remote.Files["/upload/scans/" + name]);

    private static string[] Supersedes(JsonDocument manifest) =>
        manifest.RootElement.GetProperty("run").TryGetProperty("supersedes", out var s) ? s.EnumerateArray().Select(e => e.GetString()!).ToArray() : [];

    [TestMethod]
    public async Task The_first_Run_uses_the_stable_names_without_supersedes()
    {
        var remote = new FakeRemote { WriteOnly = true };

        await Run(Settings(), remote, new FakeSource("scans").Add("a.txt", "alpha"));

        using var manifest = Manifest(remote, "manifest.json");
        Assert.IsEmpty(Supersedes(manifest));
        Assert.IsTrue(remote.Files.ContainsKey("/upload/scans/manifest.sha256"));
    }

    [TestMethod]
    public async Task When_overwrite_is_refused_the_next_Run_uploads_run_stamped_Manifest_names_that_supersede_the_earlier_one()
    {
        var remote = new FakeRemote { WriteOnly = true };
        var settings = Settings();
        await Run(settings, remote, new FakeSource("scans").Add("a.txt", "alpha"));
        var firstManifest = remote.Files["/upload/scans/manifest.json"];

        var second = await Run(settings, remote, new FakeSource("scans").Add("a.txt", "alpha").Add("b.txt", "beta"));

        Assert.AreEqual(ExitCodes.Ok, second.ExitCode, second.Reason);
        CollectionAssert.AreEqual(firstManifest, remote.Files["/upload/scans/manifest.json"], "the stable Manifest is never overwritten");
        var name = $"manifest.{second.RunId}.json";
        using var stamped = Manifest(remote, name);
        CollectionAssert.AreEqual(new[] { "manifest.json" }, Supersedes(stamped));
        Assert.AreEqual(2, stamped.RootElement.GetProperty("members").GetArrayLength(), "each Manifest is complete and cumulative");
        var flat = remote.ReadText($"/upload/scans/manifest.{second.RunId}.sha256");
        StringAssert.EndsWith(flat.TrimEnd('\n').Split('\n').Last(), "  " + name, "the flat file names the Manifest of its own Run");
    }

    [TestMethod]
    public async Task The_refusal_is_remembered_so_the_third_Run_does_not_try_the_stable_name_again()
    {
        var remote = new FakeRemote { WriteOnly = true };
        var settings = Settings();
        await Run(settings, remote, new FakeSource("scans").Add("a.txt", "alpha"));
        var second = await Run(settings, remote, new FakeSource("scans").Add("a.txt", "alpha").Add("b.txt", "beta"));
        var attemptsBefore = remote.Operations.Count(o => o.Path.Contains("/manifest.json"));

        var third = await Run(settings, remote, new FakeSource("scans").Add("a.txt", "alpha").Add("b.txt", "beta").Add("c.txt", "gamma"));

        Assert.AreEqual(attemptsBefore, remote.Operations.Count(o => o.Path.Contains("/manifest.json")), "no further attempt at the stable name");
        using var stamped = Manifest(remote, $"manifest.{third.RunId}.json");
        CollectionAssert.AreEqual(new[] { "manifest.json", $"manifest.{second.RunId}.json" }, Supersedes(stamped));
    }

    [TestMethod]
    public async Task Without_an_Upload_State_the_second_Run_still_falls_back_and_names_the_stable_Manifest_it_could_not_replace()
    {
        var remote = new FakeRemote { WriteOnly = true };
        var settings = Settings(withState: false);
        await Run(settings, remote, new FakeSource("scans").Add("a.txt", "alpha"));

        var second = await Run(settings, remote, new FakeSource("scans").Add("a.txt", "alpha"));

        using var stamped = Manifest(remote, $"manifest.{second.RunId}.json");
        CollectionAssert.AreEqual(new[] { "manifest.json" }, Supersedes(stamped));
    }

    [TestMethod]
    public async Task Direct_strategy_writes_the_run_stamped_Manifest_straight_to_its_name()
    {
        var remote = new FakeRemote { WriteOnly = true };
        var settings = Settings(strategy: UploadStrategy.Direct);
        await Run(settings, remote, new FakeSource("scans").Add("a.txt", "alpha"));

        var second = await Run(settings, remote, new FakeSource("scans").Add("a.txt", "alpha"));

        Assert.IsTrue(remote.Files.ContainsKey($"/upload/scans/manifest.{second.RunId}.json"));
        Assert.IsFalse(remote.Files.Keys.Any(k => k.EndsWith(".part")), string.Join(", ", remote.Files.Keys));
    }

    [TestMethod]
    public async Task A_server_that_can_overwrite_keeps_the_stable_names()
    {
        var remote = new FakeRemote();
        var settings = Settings() with { RemoteAccess = RemoteAccess.ReadWrite };
        await Run(settings, remote, new FakeSource("scans").Add("a.txt", "alpha"));

        var second = await Run(settings, remote, new FakeSource("scans").Add("a.txt", "alpha").Add("b.txt", "beta"));

        Assert.IsFalse(remote.Files.ContainsKey($"/upload/scans/manifest.{second.RunId}.json"));
        using var manifest = Manifest(remote, "manifest.json");
        Assert.AreEqual(2, manifest.RootElement.GetProperty("members").GetArrayLength());
        Assert.IsEmpty(Supersedes(manifest));
    }
}

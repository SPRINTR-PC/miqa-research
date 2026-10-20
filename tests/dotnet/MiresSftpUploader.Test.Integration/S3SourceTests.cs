using System.Security.Cryptography;
using System.Text.Json;
using Amazon.S3.Model;
using Microsoft.Extensions.Logging.Abstractions;
using MiresSftpUploader.Core;
using MiresSftpUploader.Test.Support;

namespace MiresSftpUploader.Test.Integration;

/// <summary>An S3 Source on a real MinIO server, through the real Engine to the in-memory remote.</summary>
[TestClass]
[TestCategory("Container")]
public sealed class S3SourceTests
{
    private string _dir = "";

    [TestInitialize]
    public void Setup() => _dir = Directory.CreateTempSubdirectory("mires-s3-").FullName;

    [TestCleanup]
    public void Cleanup()
    {
        try { Directory.Delete(_dir, recursive: true); } catch (IOException) { }
    }

    private EngineSettings Settings(ScanConfig? scan = null, params ArchiveRuleConfig[] rules) => new()
    {
        RemoteRoot = "/upload",
        Destination = "sftp.example:22",
        Retry = new RetrySettings { MaxAttempts = 1, BaseDelay = TimeSpan.Zero, MaxDelay = TimeSpan.Zero },
        State = new StateSettings { Path = Path.Combine(_dir, "state.db") },
        Scan = scan ?? new ScanConfig(),
        Archive = new ArchiveConfig { StagingPath = Path.Combine(_dir, "staging"), MinFreeSpaceBytes = 0, Rules = rules },
    };

    private static Task<RunResult> Run(EngineSettings settings, FakeRemote remote, ISource source, IProgress<RunEvent>? progress = null) =>
        new Engine(remote, [source], settings, NullLogger<Engine>.Instance, TimeProvider.System)
            .RunAsync(new RunOptions(), progress ?? new Progress<RunEvent>(), CancellationToken.None);

    private static byte[] Random(int size)
    {
        var data = new byte[size];
        RandomNumberGenerator.Fill(data);
        return data;
    }

    private static string Sha256(byte[] data) => Convert.ToHexStringLower(SHA256.HashData(data));

    private static ISource Source(MinioServerInfo server, string bucket, string? prefix = null) =>
        S3Source.Create(server.Source("bucket", bucket, prefix), server.Credentials);

    [TestMethod]
    public async Task Listing_follows_every_page_and_ignores_folder_marker_objects()
    {
        var server = MinioServer.Get();
        var objects = Enumerable.Range(0, 2_300).ToDictionary(i => $"in/d{i % 7}/f{i:D4}.txt", _ => new byte[] { 1 });
        objects["in/marker/"] = [];
        var bucket = await server.NewBucketAsync(objects);

        var listed = new List<SourceFile>();
        await foreach (var f in Source(server, bucket, "in").ListAsync(CancellationToken.None)) listed.Add(f);

        Assert.HasCount(2_300, listed);
        Assert.IsFalse(listed.Any(f => f.RelativePath.StartsWith("marker")));
        Assert.IsTrue(listed.All(f => f.ETag is { Length: > 0 } && !f.ETag.Contains('"')));
    }

    [TestMethod]
    [DataRow(0)]
    [DataRow(1)]
    [DataRow(81_921)]
    [DataRow(3_000_000)]
    public async Task Remote_content_hash_equals_manifest_hash_equals_the_object_hash(int size)
    {
        var server = MinioServer.Get();
        var data = Random(size);
        var bucket = await server.NewBucketAsync(new Dictionary<string, byte[]> { ["in/file.bin"] = data });
        var remote = new FakeRemote();

        var result = await Run(Settings(), remote, Source(server, bucket, "in"));

        Assert.AreEqual(0, result.ExitCode);
        using var manifest = JsonDocument.Parse(remote.ReadText("/upload/bucket/manifest.json"));
        Assert.AreEqual(Sha256(data), Sha256(remote.Files["/upload/bucket/file.bin"]));
        Assert.AreEqual(Sha256(data), manifest.RootElement.GetProperty("members").EnumerateArray().Single().GetProperty("sha256").GetString());
    }

    [TestMethod]
    public async Task S3_members_stream_into_the_Archive_and_their_hashes_equal_the_originals()
    {
        var server = MinioServer.Get();
        var originals = new Dictionary<string, byte[]>
        {
            ["slide/tile-1.jpg"] = Random(3_000_000),
            ["slide/tile-2.jpg"] = Random(81_921),
            ["slide/tile-3.jpg"] = [],
        };
        var bucket = await server.NewBucketAsync(originals);
        var remote = new FakeRemote();
        var rule = new ArchiveRuleConfig { Name = "tiles", Pattern = @"\.jpg$", ArchiveName = "{rule}.zip" };

        var result = await Run(Settings(rules: rule), remote, Source(server, bucket));

        Assert.AreEqual(0, result.ExitCode);
        var zip = remote.Files["/upload/bucket/slide/tiles.zip"];
        using var manifest = JsonDocument.Parse(remote.ReadText("/upload/bucket/manifest.json"));
        var archive = MiresSftpUploader.Test.Support.ManifestTree.Archives(manifest.RootElement).Values.Single();
        Assert.AreEqual(Sha256(zip), archive.GetProperty("sha256").GetString());
        var listed = archive.GetProperty("members").EnumerateArray().ToDictionary(
            m => m.GetProperty("path").GetString()!, m => m.GetProperty("sha256").GetString());
        using var opened = new System.IO.Compression.ZipArchive(new MemoryStream(zip), System.IO.Compression.ZipArchiveMode.Read);
        foreach (var (path, data) in originals)
        {
            using var member = opened.GetEntry(path["slide/".Length..])!.Open();
            using var copy = new MemoryStream();
            await member.CopyToAsync(copy);
            Assert.AreEqual(Sha256(data), listed[path]);
            Assert.AreEqual(Sha256(data), Sha256(copy.ToArray()));
        }
        Assert.IsEmpty(Directory.GetFileSystemEntries(Path.Combine(_dir, "staging")), "no separate download is left behind");
    }

    [TestMethod]
    public async Task An_S3_member_overwritten_while_the_Archive_is_built_fails_it_with_ChangedDuringArchive()
    {
        var server = MinioServer.Get();
        var bucket = await server.NewBucketAsync(new Dictionary<string, byte[]> { ["d/a.jpg"] = Bytes("alpha"), ["d/b.jpg"] = Bytes("beta") });
        using var admin = server.AdminClient();
        var source = new AfterOpenSource(Source(server, bucket), path =>
        {
            if (path == "d/b.jpg")
                admin.PutObjectAsync(new PutObjectRequest { BucketName = bucket, Key = "d/b.jpg", InputStream = new MemoryStream(Bytes("omega!")) }).GetAwaiter().GetResult();
        });
        var seen = new List<RunEvent>();
        var rule = new ArchiveRuleConfig { Name = "tiles", Pattern = @"\.jpg$" };
        var remote = new FakeRemote();

        var result = await Run(Settings(rules: rule), remote, source, new Sync(seen.Add));

        Assert.AreEqual(1, result.ExitCode);
        StringAssert.Contains(seen.OfType<FileOutcomeChanged>().Last(e => e.RelativePath == "d/b.jpg").Reason, "ChangedDuringArchive");
        Assert.IsFalse(remote.Files.Keys.Any(k => k.EndsWith(".zip")));
    }

    [TestMethod]
    public async Task A_repeated_Run_skips_unchanged_objects_and_uploads_an_overwritten_one_even_of_the_same_size()
    {
        var server = MinioServer.Get();
        var bucket = await server.NewBucketAsync(new Dictionary<string, byte[]> { ["a.txt"] = Bytes("alpha"), ["b.txt"] = Bytes("beta") });
        var remote = new FakeRemote();
        var settings = Settings();
        await Run(settings, remote, Source(server, bucket));

        using var admin = server.AdminClient();
        await admin.PutObjectAsync(new PutObjectRequest { BucketName = bucket, Key = "b.txt", InputStream = new MemoryStream(Bytes("BETA")) });
        var second = await Run(settings, remote, Source(server, bucket));

        Assert.AreEqual(1, second.Count(FileOutcome.Skipped));
        Assert.AreEqual(1, second.Count(FileOutcome.Succeeded));
        Assert.AreEqual("BETA", remote.ReadText("/upload/bucket/b.txt"));
    }

    [TestMethod]
    public async Task Scan_min_age_uses_the_objects_LastModified()
    {
        var server = MinioServer.Get();
        var bucket = await server.NewBucketAsync(new Dictionary<string, byte[]> { ["fresh.txt"] = Bytes("fresh") });
        var seen = new List<RunEvent>();

        var result = await Run(Settings(new ScanConfig { MinFileAgeSeconds = 3600 }), new FakeRemote(), Source(server, bucket), new Sync(seen.Add));

        Assert.AreEqual(1, result.Count(FileOutcome.Skipped));
        Assert.AreEqual("TooRecent", seen.OfType<FileOutcomeChanged>().Last(e => e.RelativePath == "fresh.txt").Reason);
    }

    private static byte[] Bytes(string text) => System.Text.Encoding.UTF8.GetBytes(text);

    private sealed class Sync(Action<RunEvent> onReport) : IProgress<RunEvent>
    {
        public void Report(RunEvent value) { lock (this) onReport(value); }
    }

    /// <summary>Delegates to a real Source and lets a test act right after a file was opened.</summary>
    private sealed class AfterOpenSource(ISource inner, Action<string> afterOpen) : ISource
    {
        public string Name => inner.Name;
        public string? RemotePath => inner.RemotePath;
        public IAsyncEnumerable<SourceFile> ListAsync(CancellationToken ct) => inner.ListAsync(ct);
        public Task<SourceFile?> StatAsync(string relativePath, CancellationToken ct) => inner.StatAsync(relativePath, ct);

        public async Task<Stream> OpenReadAsync(string relativePath, CancellationToken ct)
        {
            var stream = await inner.OpenReadAsync(relativePath, ct);
            afterOpen(relativePath);
            return stream;
        }
    }
}

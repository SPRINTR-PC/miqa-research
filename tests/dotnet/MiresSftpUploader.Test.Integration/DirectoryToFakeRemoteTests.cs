using System.Security.Cryptography;
using System.Text.Json;
using Microsoft.Extensions.Logging.Abstractions;
using MiresSftpUploader.Core;
using MiresSftpUploader.Test.Support;

namespace MiresSftpUploader.Test.Integration;

/// <summary>Real temp directory through the real Engine to the in-memory remote. Container tests against OpenSSH come in a later ticket.</summary>
[TestClass]
public sealed class DirectoryToFakeRemoteTests
{
    [TestMethod]
    [DataRow(0)]
    [DataRow(1)]
    [DataRow(81_920)]
    [DataRow(81_921)]
    [DataRow(3_000_000)]
    public async Task Remote_content_hash_equals_manifest_hash_equals_local_hash(int size)
    {
        var root = Directory.CreateTempSubdirectory("mires-it-").FullName;
        try
        {
            var data = new byte[size];
            RandomNumberGenerator.Fill(data);
            await File.WriteAllBytesAsync(Path.Combine(root, "file.bin"), data);
            var remote = new FakeRemote();
            var engine = new Engine(remote, [new DirectorySource("scans", root)],
                new EngineSettings { RemoteRoot = "/upload" }, NullLogger<Engine>.Instance, TimeProvider.System);

            var result = await engine.RunAsync(new RunOptions(), new Progress<RunEvent>(), CancellationToken.None);

            Assert.AreEqual(0, result.ExitCode);
            var local = Convert.ToHexStringLower(SHA256.HashData(data));
            var uploaded = Convert.ToHexStringLower(SHA256.HashData(remote.Files["/upload/scans/file.bin"]));
            using var manifest = JsonDocument.Parse(remote.ReadText("/upload/scans/manifest.json"));
            var inManifest = manifest.RootElement.GetProperty("members").EnumerateArray().Single().GetProperty("sha256").GetString();
            Assert.AreEqual(local, uploaded);
            Assert.AreEqual(local, inManifest);
        }
        finally
        {
            Directory.Delete(root, recursive: true);
        }
    }

    [TestMethod]
    public async Task Remote_archive_hash_equals_manifest_hash_and_each_member_hash_equals_its_original()
    {
        var root = Directory.CreateTempSubdirectory("mires-it-archive-").FullName;
        var staging = Directory.CreateTempSubdirectory("mires-it-staging-").FullName;
        try
        {
            var originals = new Dictionary<string, byte[]>
            {
                ["slide/tile-1.jpg"] = new byte[3_000_000],
                ["slide/tile-2.jpg"] = new byte[81_921],
                ["slide/tile-3.jpg"] = [],
            };
            foreach (var (path, data) in originals)
            {
                RandomNumberGenerator.Fill(data);
                Directory.CreateDirectory(Path.GetDirectoryName(Path.Combine(root, path))!);
                await File.WriteAllBytesAsync(Path.Combine(root, path), data);
            }
            var remote = new FakeRemote();
            var settings = new EngineSettings
            {
                RemoteRoot = "/upload",
                Archive = new ArchiveConfig
                {
                    StagingPath = staging,
                    MinFreeSpaceBytes = 0,
                    Rules = [new ArchiveRuleConfig { Name = "tiles", Pattern = @"\.jpg$", ArchiveName = "{rule}.zip" }],
                },
            };
            var engine = new Engine(remote, [new DirectorySource("scans", root)], settings, NullLogger<Engine>.Instance, TimeProvider.System);

            var result = await engine.RunAsync(new RunOptions(), new Progress<RunEvent>(), CancellationToken.None);

            Assert.AreEqual(0, result.ExitCode);
            var zip = remote.Files["/upload/scans/slide/tiles.zip"];
            using var manifest = JsonDocument.Parse(remote.ReadText("/upload/scans/manifest.json"));
            var archive = MiresSftpUploader.Test.Support.ManifestTree.Archives(manifest.RootElement).Values.Single();
            Assert.AreEqual(Convert.ToHexStringLower(SHA256.HashData(zip)), archive.GetProperty("sha256").GetString());
            var listed = archive.GetProperty("members").EnumerateArray().ToDictionary(
                m => m.GetProperty("path").GetString()!, m => m.GetProperty("sha256").GetString());
            using var opened = new System.IO.Compression.ZipArchive(new MemoryStream(zip), System.IO.Compression.ZipArchiveMode.Read);
            foreach (var (path, data) in originals)
            {
                var original = Convert.ToHexStringLower(SHA256.HashData(data));
                using var member = opened.GetEntry(path["slide/".Length..])!.Open();
                using var copy = new MemoryStream();
                await member.CopyToAsync(copy);
                Assert.AreEqual(original, listed[path], $"Manifest member hash of {path}");
                Assert.AreEqual(original, Convert.ToHexStringLower(SHA256.HashData(copy.ToArray())), $"zip entry {path}");
            }
            Assert.IsEmpty(Directory.GetFileSystemEntries(staging), "the Staging Area is gone after the Run");
        }
        finally
        {
            Directory.Delete(root, recursive: true);
            Directory.Delete(staging, recursive: true);
        }
    }

    [TestMethod]
    public async Task Dry_run_over_a_real_directory_leaves_directory_and_database_unchanged()
    {
        var root = Directory.CreateTempSubdirectory("mires-it-dry-").FullName;
        var data = Directory.CreateTempSubdirectory("mires-it-state-").FullName;
        try
        {
            await File.WriteAllTextAsync(Path.Combine(root, "a.txt"), "alpha");
            await File.WriteAllTextAsync(Path.Combine(root, ".DS_Store"), "junk");
            await File.WriteAllTextAsync(Path.Combine(root, "fresh.txt"), "fresh");
            File.SetLastWriteTimeUtc(Path.Combine(root, "a.txt"), DateTime.UtcNow.AddDays(-2));
            var settings = new EngineSettings
            {
                RemoteRoot = "/upload",
                State = new StateSettings { Path = Path.Combine(data, "state.db") },
                Scan = new ScanConfig { MinFileAgeSeconds = 3600 },
            };
            var remote = new FakeRemote();
            var engine = new Engine(remote, [new DirectorySource("scans", root)], settings, NullLogger<Engine>.Instance, TimeProvider.System);
            await engine.RunAsync(new RunOptions(), new Progress<RunEvent>(), CancellationToken.None);
            var rootBefore = Snapshot(root);
            var dataBefore = Snapshot(data);

            var result = await engine.RunAsync(new RunOptions { DryRun = true }, new Progress<RunEvent>(), CancellationToken.None);

            Assert.AreEqual(0, result.ExitCode);
            Assert.AreEqual(1, result.Count(FileOutcome.Ignored));
            Assert.AreEqual(2, result.Count(FileOutcome.Skipped), "a.txt unchanged, fresh.txt Too Recent");
            CollectionAssert.AreEquivalent(rootBefore, Snapshot(root));
            CollectionAssert.AreEquivalent(dataBefore, Snapshot(data));
        }
        finally
        {
            Directory.Delete(root, recursive: true);
            Directory.Delete(data, recursive: true);
        }
    }

    private static Dictionary<string, string> Snapshot(string directory) =>
        Directory.EnumerateFiles(directory, "*", SearchOption.AllDirectories).ToDictionary(
            f => Path.GetRelativePath(directory, f),
            f => $"{Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(f)))}@{File.GetLastWriteTimeUtc(f).Ticks}");
}

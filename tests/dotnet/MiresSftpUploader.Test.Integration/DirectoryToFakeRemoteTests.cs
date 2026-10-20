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
            var inManifest = manifest.RootElement.GetProperty("files").EnumerateArray().Single().GetProperty("sha256").GetString();
            Assert.AreEqual(local, uploaded);
            Assert.AreEqual(local, inManifest);
        }
        finally
        {
            Directory.Delete(root, recursive: true);
        }
    }
}

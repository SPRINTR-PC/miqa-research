using System.Security.Cryptography;
using System.Text.Json;
using Microsoft.Extensions.Logging.Abstractions;
using MiresSftpUploader.Core;

namespace MiresSftpUploader.Test.Integration;

/// <summary>
/// The hash proof: uploading through <c>.part</c> plus rename does not change the file.
/// The hash the server's file system has equals the Manifest hash equals the local hash.
/// </summary>
[TestClass]
[TestCategory("Container")]
public sealed class SftpHashProofTests
{
    internal static Engine NewEngine(SftpServerInfo server, string remoteRoot, params ISource[] sources) =>
        new(new SshNetRemote(server.Connection()), sources,
            new EngineSettings
            {
                RemoteRoot = remoteRoot,
                Destination = $"{server.Host}:{server.Port}",
                Retry = new RetrySettings { MaxAttempts = 3, BaseDelay = TimeSpan.Zero, MaxDelay = TimeSpan.Zero },
            },
            NullLogger<Engine>.Instance, TimeProvider.System);

    internal static string NewRemoteRoot(SftpServerInfo server) => $"{server.UploadDirectory}/proof-{Guid.NewGuid():N}";

    internal static async Task<string> ManifestHashAsync(string manifestPath, string file)
    {
        using var manifest = JsonDocument.Parse(await SftpServer.RemoteReadTextAsync(manifestPath));
        return manifest.RootElement.GetProperty("members").EnumerateArray()
            .Single(f => f.GetProperty("path").GetString() == file).GetProperty("sha256").GetString()!;
    }

    private static async Task AssertProofAsync(long size)
    {
        var server = SftpServer.Get();
        var directory = Directory.CreateTempSubdirectory("mires-proof-").FullName;
        try
        {
            var path = Path.Combine(directory, "file.bin");
            await WriteRandomAsync(path, size);
            var local = await HashFileAsync(path);
            var remoteRoot = NewRemoteRoot(server);

            var result = await NewEngine(server, remoteRoot, new DirectorySource("scans", directory))
                .RunAsync(new RunOptions(), new Progress<RunEvent>(), CancellationToken.None);

            Assert.AreEqual(0, result.ExitCode, result.Reason);
            Assert.AreEqual(1, result.Count(FileOutcome.Succeeded));
            Assert.AreEqual(local, await SftpServer.RemoteSha256Async(remoteRoot + "/scans/file.bin"), "remote hash");
            Assert.AreEqual(local, await ManifestHashAsync(remoteRoot + "/scans/manifest.json", "file.bin"), "Manifest hash");
            Assert.IsFalse((await SftpServer.RemoteFilesAsync(remoteRoot)).Any(f => f.EndsWith(".part")), "no .part may remain");
        }
        finally
        {
            Directory.Delete(directory, recursive: true);
        }
    }

    [TestMethod]
    [DataRow(0)]
    [DataRow(1)]
    [DataRow(32_768)]
    [DataRow(32_769)]
    [DataRow(81_920)]
    [DataRow(81_921)]
    [DataRow(64 * 1024 * 1024)]
    public Task Remote_hash_equals_Manifest_hash_equals_local_hash(int size) => AssertProofAsync(size);

    [TestMethod]
    [TestCategory("Scale")]
    public async Task Four_GiB_file_keeps_its_hash()
    {
        if (Environment.GetEnvironmentVariable("MIRES_TEST_4GIB") != "1")
            Assert.Inconclusive("Set MIRES_TEST_4GIB=1 to run the 4 GiB hash proof.");
        await AssertProofAsync(4L * 1024 * 1024 * 1024);
    }

    internal static async Task WriteRandomAsync(string path, long size)
    {
        await using var file = File.Create(path);
        var buffer = new byte[1024 * 1024];
        for (var written = 0L; written < size; written += buffer.Length)
        {
            RandomNumberGenerator.Fill(buffer);
            await file.WriteAsync(buffer.AsMemory(0, (int)Math.Min(buffer.Length, size - written)));
        }
    }

    internal static async Task<string> HashFileAsync(string path)
    {
        await using var file = File.OpenRead(path);
        return Convert.ToHexStringLower(await SHA256.HashDataAsync(file));
    }
}

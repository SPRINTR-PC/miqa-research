using System.IO.Compression;
using MiresSftpUploader.Core;

namespace MiresSftpUploader.Test.Unit;

/// <summary>
/// The Zip64 structures only matter beyond 4 GiB or 65,535 entries. The writer decides on the declared size,
/// so a small stream with a large declared size exercises the same structures cheaply.
/// </summary>
[TestClass]
public sealed class DeterministicZipWriterTests
{
    private static async Task<byte[]> WriteAsync(IEnumerable<(string Name, long Declared, byte[] Content)> entries)
    {
        using var output = new MemoryStream();
        using var writer = new DeterministicZipWriter(output);
        foreach (var (name, declared, content) in entries)
            await writer.AddAsync(name, declared, new MemoryStream(content), CancellationToken.None);
        await writer.FinishAsync(CancellationToken.None);
        return output.ToArray();
    }

    [TestMethod]
    public async Task An_entry_declared_beyond_4_GiB_gets_Zip64_fields_that_standard_readers_accept()
    {
        var zip = await WriteAsync([("small.txt", 5, "hello"u8.ToArray()), ("huge.bin", 5L * 1024 * 1024 * 1024, "world"u8.ToArray())]);

        using var archive = new ZipArchive(new MemoryStream(zip), ZipArchiveMode.Read);
        foreach (var entry in archive.Entries)
        {
            using var reader = new StreamReader(entry.Open());
            Assert.AreEqual(entry.Name == "small.txt" ? "hello" : "world", await reader.ReadToEndAsync());
        }
    }

    [TestMethod]
    public async Task Sixty_five_thousand_entries_need_the_Zip64_end_of_central_directory()
    {
        var zip = await WriteAsync(Enumerable.Range(0, 70_000).Select(i => ($"f{i:D5}", 0L, Array.Empty<byte>())));

        using var archive = new ZipArchive(new MemoryStream(zip), ZipArchiveMode.Read);
        Assert.HasCount(70_000, archive.Entries);
        Assert.AreEqual("f69999", archive.Entries[^1].FullName);
    }
}

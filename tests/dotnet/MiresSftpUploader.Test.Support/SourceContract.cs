using MiresSftpUploader.Core;

namespace MiresSftpUploader.Test.Support;

/// <summary>Behaviour every <see cref="ISource"/> adapter must have. Derive once per adapter.</summary>
[TestClass]
public abstract class SourceContract
{
    /// <summary>Creates a Source named "contract" holding exactly <paramref name="files"/> (forward-slash relative paths).</summary>
    protected abstract ISource CreateSource(IReadOnlyDictionary<string, byte[]> files);

    private static async Task<List<SourceFile>> ListAll(ISource source)
    {
        var all = new List<SourceFile>();
        await foreach (var f in source.ListAsync(CancellationToken.None)) all.Add(f);
        return all;
    }

    [TestMethod]
    public async Task Lists_every_file_recursively_with_forward_slash_paths_and_sizes()
    {
        var source = CreateSource(new Dictionary<string, byte[]>
        {
            ["a.txt"] = [1, 2, 3],
            ["dir/b.txt"] = [],
            ["dir/sub/c.txt"] = [9],
        });

        var listed = (await ListAll(source)).OrderBy(f => f.RelativePath, StringComparer.Ordinal).ToList();

        CollectionAssert.AreEqual(new[] { "a.txt", "dir/b.txt", "dir/sub/c.txt" }, listed.Select(f => f.RelativePath).ToArray());
        CollectionAssert.AreEqual(new long[] { 3, 0, 1 }, listed.Select(f => f.Size).ToArray());
    }

    [TestMethod]
    public async Task Open_read_returns_the_file_content()
    {
        var source = CreateSource(new Dictionary<string, byte[]> { ["dir/a.bin"] = [5, 6, 7] });

        await using var stream = await source.OpenReadAsync("dir/a.bin", CancellationToken.None);
        using var copy = new MemoryStream();
        await stream.CopyToAsync(copy);

        CollectionAssert.AreEqual(new byte[] { 5, 6, 7 }, copy.ToArray());
    }

    [TestMethod]
    public async Task Stat_reports_the_listed_size_and_time_and_null_for_a_missing_file()
    {
        var source = CreateSource(new Dictionary<string, byte[]> { ["dir/a.bin"] = [5, 6, 7] });
        var listed = (await ListAll(source)).Single();

        var stat = await source.StatAsync("dir/a.bin", CancellationToken.None);

        Assert.AreEqual(listed, stat);
        Assert.IsNull(await source.StatAsync("dir/missing.bin", CancellationToken.None));
    }

    [TestMethod]
    public async Task An_empty_source_lists_nothing()
    {
        var source = CreateSource(new Dictionary<string, byte[]>());

        Assert.IsEmpty(await ListAll(source));
    }
}

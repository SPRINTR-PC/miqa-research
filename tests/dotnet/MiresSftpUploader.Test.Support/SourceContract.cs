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
    public async Task Stat_describes_one_file_without_listing_the_source_and_is_null_for_a_vanished_one()
    {
        var source = CreateSource(new Dictionary<string, byte[]> { ["dir/a.bin"] = [5, 6, 7], ["b.bin"] = [] });
        var listed = (await ListAll(source)).Single(f => f.RelativePath == "dir/a.bin");

        var stat = await source.StatAsync("dir/a.bin", CancellationToken.None);

        Assert.IsNotNull(stat);
        Assert.AreEqual("dir/a.bin", stat.RelativePath);
        Assert.AreEqual(3, stat.Size);
        Assert.AreEqual(listed.Modified, stat.Modified);
        Assert.IsNull(await source.StatAsync("dir/gone.bin", CancellationToken.None));
    }

    /// <summary>A Post-upload Move target of the adapter's own type: a new, empty location on the same endpoint.</summary>
    protected abstract MoveTargetConfig CreateMoveTarget();

    /// <summary>Reads a file from a move target independently of the adapter; null when it is not there.</summary>
    protected abstract byte[]? ReadMoveTarget(MoveTargetConfig target, string relativePath);

    /// <summary>Puts a file into a move target independently of the adapter.</summary>
    protected abstract void PutMoveTarget(MoveTargetConfig target, string relativePath, byte[] data);

    [TestMethod]
    public async Task Move_puts_the_file_under_the_target_with_its_relative_path_and_removes_it_from_the_source()
    {
        var source = CreateSource(new Dictionary<string, byte[]> { ["dir/sub/a.bin"] = [5, 6, 7], ["b.bin"] = [1] });
        var target = CreateMoveTarget();

        var result = await source.MoveAsync("dir/sub/a.bin", target, CancellationToken.None);

        Assert.AreEqual(MoveStatus.Moved, result.Status, result.Detail);
        CollectionAssert.AreEqual(new byte[] { 5, 6, 7 }, ReadMoveTarget(target, "dir/sub/a.bin"));
        Assert.IsNull(await source.StatAsync("dir/sub/a.bin", CancellationToken.None));
        Assert.IsNotNull(await source.StatAsync("b.bin", CancellationToken.None));
    }

    [TestMethod]
    public async Task Move_never_overwrites_an_existing_target_file()
    {
        var source = CreateSource(new Dictionary<string, byte[]> { ["a.bin"] = [5, 6, 7] });
        var target = CreateMoveTarget();
        PutMoveTarget(target, "a.bin", [9, 9]);

        var result = await source.MoveAsync("a.bin", target, CancellationToken.None);

        Assert.AreEqual(MoveStatus.TargetExists, result.Status);
        CollectionAssert.AreEqual(new byte[] { 9, 9 }, ReadMoveTarget(target, "a.bin"));
        Assert.IsNotNull(await source.StatAsync("a.bin", CancellationToken.None));
    }

    [TestMethod]
    public async Task Move_of_a_file_that_is_not_there_fails()
    {
        var source = CreateSource(new Dictionary<string, byte[]> { ["a.bin"] = [1] });

        var result = await source.MoveAsync("gone.bin", CreateMoveTarget(), CancellationToken.None);

        Assert.AreEqual(MoveStatus.Failed, result.Status);
    }

    [TestMethod]
    public async Task An_empty_source_lists_nothing()
    {
        var source = CreateSource(new Dictionary<string, byte[]>());

        Assert.IsEmpty(await ListAll(source));
    }
}

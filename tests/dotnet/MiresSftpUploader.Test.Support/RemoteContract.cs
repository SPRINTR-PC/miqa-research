using MiresSftpUploader.Core;

namespace MiresSftpUploader.Test.Support;

/// <summary>Behaviour every <see cref="IRemote"/> adapter must have. Derive once per adapter (fake, SFTP).</summary>
[TestClass]
public abstract class RemoteContract
{
    /// <summary>Creates a remote that can write below <see cref="RootDirectory"/>.</summary>
    protected abstract IRemote CreateRemote();

    /// <summary>The writable directory the contract works in; "" for a server whose root is writable.</summary>
    protected virtual string RootDirectory => "";

    /// <summary>A directory name that is unique per call, so adapters sharing a server do not collide.</summary>
    protected string UniqueDirectory() => RootDirectory + "/contract-" + Guid.NewGuid().ToString("N");

    private static async Task<IRemoteSession> Connect(IRemote remote)
    {
        var connect = await remote.ConnectAsync(CancellationToken.None);
        Assert.IsTrue(connect.IsOk, connect.Reason);
        return connect.Value!;
    }

    [TestMethod]
    public async Task Uploaded_content_can_be_statted_by_size()
    {
        await using var session = await Connect(CreateRemote());
        var dir = UniqueDirectory() + "/nested/deep";
        Assert.IsTrue((await session.EnsureDirectoryAsync(dir, CancellationToken.None)).IsOk);

        var upload = await session.UploadAsync(new MemoryStream([1, 2, 3, 4]), dir + "/f.bin", CancellationToken.None);
        var stat = await session.StatAsync(dir + "/f.bin", CancellationToken.None);

        Assert.IsTrue(upload.IsOk, upload.Reason);
        Assert.IsTrue(stat.IsOk);
        Assert.AreEqual(4, stat.Value!.Size);
    }

    [TestMethod]
    public async Task Ensure_directory_is_idempotent()
    {
        await using var session = await Connect(CreateRemote());
        var dir = UniqueDirectory() + "/a/b";

        Assert.IsTrue((await session.EnsureDirectoryAsync(dir, CancellationToken.None)).IsOk);
        Assert.IsTrue((await session.EnsureDirectoryAsync(dir, CancellationToken.None)).IsOk);
    }

    [TestMethod]
    public async Task Stat_of_a_missing_object_is_not_ok()
    {
        await using var session = await Connect(CreateRemote());

        var stat = await session.StatAsync(UniqueDirectory() + "/missing", CancellationToken.None);

        Assert.IsFalse(stat.IsOk);
    }

    [TestMethod]
    public async Task Rename_moves_the_object_and_can_overwrite()
    {
        await using var session = await Connect(CreateRemote());
        var dir = UniqueDirectory();
        await session.EnsureDirectoryAsync(dir, CancellationToken.None);
        await session.UploadAsync(new MemoryStream([1]), dir + "/old.part", CancellationToken.None);
        await session.UploadAsync(new MemoryStream([1, 2]), dir + "/final", CancellationToken.None);

        var rename = await session.RenameAsync(dir + "/old.part", dir + "/final", overwrite: true, CancellationToken.None);

        Assert.IsTrue(rename.IsOk, rename.Reason);
        Assert.IsFalse((await session.StatAsync(dir + "/old.part", CancellationToken.None)).IsOk);
        Assert.AreEqual(1, (await session.StatAsync(dir + "/final", CancellationToken.None)).Value!.Size);
    }

    [TestMethod]
    public async Task Delete_removes_the_object()
    {
        await using var session = await Connect(CreateRemote());
        var dir = UniqueDirectory();
        await session.EnsureDirectoryAsync(dir, CancellationToken.None);
        await session.UploadAsync(new MemoryStream([1]), dir + "/f", CancellationToken.None);

        var delete = await session.DeleteAsync(dir + "/f", CancellationToken.None);

        Assert.IsTrue(delete.IsOk, delete.Reason);
        Assert.IsFalse((await session.StatAsync(dir + "/f", CancellationToken.None)).IsOk);
    }
}

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

    [TestMethod]
    public async Task Upload_progress_is_monotonic_and_ends_at_the_size_of_the_object()
    {
        await using var session = await Connect(CreateRemote());
        var dir = UniqueDirectory();
        await session.EnsureDirectoryAsync(dir, CancellationToken.None);
        var payload = new byte[300_000];
        new Random(11).NextBytes(payload);
        var reports = new RecordingProgress();

        var upload = await session.UploadAsync(new MemoryStream(payload), dir + "/f.bin", CancellationToken.None, reports);

        Assert.IsTrue(upload.IsOk, upload.Reason);
        var seen = reports.Values;
        Assert.IsNotEmpty(seen);
        for (var i = 1; i < seen.Count; i++) Assert.IsGreaterThan(seen[i - 1], seen[i], "reports never move backwards");
        Assert.AreEqual(payload.Length, seen[^1]);
    }

    private sealed class RecordingProgress : IProgress<long>
    {
        private readonly object _gate = new();
        private readonly List<long> _values = [];

        public IReadOnlyList<long> Values
        {
            get { lock (_gate) return _values.ToArray(); }
        }

        public void Report(long value)
        {
            lock (_gate) _values.Add(value);
        }
    }

    [TestMethod]
    public async Task Download_returns_the_uploaded_bytes()
    {
        await using var session = await Connect(CreateRemote());
        var dir = UniqueDirectory();
        await session.EnsureDirectoryAsync(dir, CancellationToken.None);
        var payload = new byte[100_000];
        new Random(7).NextBytes(payload);
        await session.UploadAsync(new MemoryStream(payload), dir + "/f.bin", CancellationToken.None);

        var received = new MemoryStream();
        var download = await session.DownloadAsync(dir + "/f.bin", received, CancellationToken.None);

        Assert.IsTrue(download.IsOk, download.Reason);
        CollectionAssert.AreEqual(payload, received.ToArray());
    }

    [TestMethod]
    public async Task Download_of_a_missing_object_is_not_ok()
    {
        await using var session = await Connect(CreateRemote());

        var download = await session.DownloadAsync(UniqueDirectory() + "/missing", new MemoryStream(), CancellationToken.None);

        Assert.IsFalse(download.IsOk);
    }

    [TestMethod]
    public async Task List_names_the_entries_of_a_directory()
    {
        await using var session = await Connect(CreateRemote());
        var dir = UniqueDirectory();
        await session.EnsureDirectoryAsync(dir + "/sub", CancellationToken.None);
        await session.UploadAsync(new MemoryStream([1]), dir + "/f.bin", CancellationToken.None);

        var list = await session.ListAsync(dir, CancellationToken.None);

        Assert.IsTrue(list.IsOk, list.Reason);
        CollectionAssert.AreEquivalent(new[] { "f.bin", "sub" }, list.Value!.ToArray());
    }

    [TestMethod]
    public async Task List_of_a_missing_directory_is_not_ok()
    {
        await using var session = await Connect(CreateRemote());

        var list = await session.ListAsync(UniqueDirectory() + "/missing", CancellationToken.None);

        Assert.IsFalse(list.IsOk);
    }
}

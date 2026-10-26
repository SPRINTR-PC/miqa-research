using Microsoft.Data.Sqlite;
using Microsoft.Extensions.Logging.Abstractions;
using MiresSftpUploader.Core;
using MiresSftpUploader.Test.Support;

namespace MiresSftpUploader.Test.Unit;

/// <summary>Files the app creates in the Data Directory are group-writable whatever the account's umask is (Linux and macOS).</summary>
[TestClass]
[System.Runtime.Versioning.UnsupportedOSPlatform("windows")]
public sealed class DataDirectoryFilesTests
{
    private const UnixFileMode Rw0660 = UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.GroupRead | UnixFileMode.GroupWrite;

    private string _dir = "";

    [TestInitialize]
    public void Setup()
    {
        if (OperatingSystem.IsWindows()) Assert.Inconclusive("Unix permission semantics.");
        _dir = Directory.CreateTempSubdirectory("mires-files-").FullName;
    }

    [TestCleanup]
    public void Cleanup()
    {
        try { Directory.Delete(_dir, recursive: true); } catch (IOException) { }
    }

    private async Task RunOnce()
    {
        var settings = new EngineSettings { Destination = "sftp.example:22", State = new StateSettings { AccessGroup = TestAccessGroup.Name, Path = DataDirectory.DatabasePath(_dir) } };
        var engine = new Engine(new FakeRemote(), [new FakeSource("scans").Add("a.txt", "alpha")], settings,
            NullLogger<Engine>.Instance, TimeProvider.System);
        var result = await engine.RunAsync(new RunOptions(), new Progress<RunEvent>(), CancellationToken.None);
        Assert.AreEqual(0, result.ExitCode, result.Reason);
    }

    [TestMethod]
    public async Task Database_and_lock_are_created_group_writable()
    {
        await RunOnce();

        var database = DataDirectory.DatabasePath(_dir);
        Assert.AreEqual(Rw0660, File.GetUnixFileMode(database));
        Assert.AreEqual(Rw0660, File.GetUnixFileMode(database + ".lock"));
    }

    [TestMethod]
    public async Task Wal_and_shm_files_inherit_the_group_writable_mode()
    {
        await RunOnce();
        var database = DataDirectory.DatabasePath(_dir);

        using var connection = new SqliteConnection($"Data Source={database};Pooling=False");
        connection.Open();
        using var command = connection.CreateCommand();
        command.CommandText = "SELECT count(*) FROM Runs";
        Assert.AreEqual(1L, command.ExecuteScalar());

        Assert.AreEqual(Rw0660, File.GetUnixFileMode(database + "-wal"));
        Assert.AreEqual(Rw0660, File.GetUnixFileMode(database + "-shm"));
    }
}

using MiresSftpUploader.Core;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class DataDirectoryAccessTests
{
    private string _root = "";

    [TestInitialize]
    public void Setup() => _root = Directory.CreateTempSubdirectory("mires-access-").FullName;

    [TestCleanup]
    public void Cleanup()
    {
        if (!OperatingSystem.IsWindows())
            File.SetUnixFileMode(_root, UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute);
        try { Directory.Delete(_root, recursive: true); } catch (IOException) { }
    }

    [TestMethod]
    public void Writable_directory_reports_path_account_database_size_and_free_space()
    {
        File.WriteAllBytes(DataDirectory.DatabasePath(_root), new byte[4096]);

        var access = DataDirectory.Check(_root);

        Assert.IsTrue(access.Writable);
        Assert.IsNull(access.Problem);
        Assert.AreEqual(_root, access.Path);
        Assert.AreEqual(Environment.UserName, access.Account);
        Assert.AreEqual(4096, access.DatabaseSizeBytes);
        Assert.IsGreaterThan(0, access.FreeSpaceBytes);
    }

    [TestMethod]
    public void Check_leaves_nothing_behind()
    {
        DataDirectory.Check(_root);

        Assert.IsEmpty(Directory.GetFileSystemEntries(_root));
    }

    [TestMethod]
    public void Missing_directory_names_the_path_the_account_and_the_fix_command()
    {
        var missing = Path.Combine(_root, "absent");

        var access = DataDirectory.Check(missing);

        Assert.IsFalse(access.Writable);
        StringAssert.Contains(access.Problem, missing);
        StringAssert.Contains(access.Problem, Environment.UserName);
        StringAssert.Contains(access.Problem, "--init-data-dir");
        StringAssert.Contains(access.FixCommand, "--init-data-dir");
    }

    [TestMethod]
    public void Unwritable_directory_is_reported_the_same_way()
    {
        if (OperatingSystem.IsWindows() || Environment.UserName == "root") Assert.Inconclusive("Needs a non-root Unix account.");
        File.SetUnixFileMode(_root, UnixFileMode.UserRead | UnixFileMode.UserExecute);

        var access = DataDirectory.Check(_root);

        Assert.IsFalse(access.Writable);
        StringAssert.Contains(access.Problem, _root);
        StringAssert.Contains(access.Problem, "not writable");
    }
}

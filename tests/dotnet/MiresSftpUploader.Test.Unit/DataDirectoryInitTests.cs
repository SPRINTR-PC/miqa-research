using System.Diagnostics;
using MiresSftpUploader.Core;

namespace MiresSftpUploader.Test.Unit;

/// <summary>
/// --init-data-dir on Linux and macOS. The tests use the current user's own primary group, because they cannot
/// assume a mires-uploader or staff membership; the group lookup and chgrp are the same code path.
/// </summary>
[TestClass]
[System.Runtime.Versioning.UnsupportedOSPlatform("windows")]
public sealed class DataDirectoryInitTests
{
    private const UnixFileMode SetGid = UnixFileMode.SetGroup;
    private const UnixFileMode Rwx2770 = SetGid | UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute
        | UnixFileMode.GroupRead | UnixFileMode.GroupWrite | UnixFileMode.GroupExecute;

    private string _root = "";
    private static string MyGroup => Shell("id", "-gn");

    [TestInitialize]
    public void Setup()
    {
        if (OperatingSystem.IsWindows()) Assert.Inconclusive("Unix permission semantics.");
        _root = Directory.CreateTempSubdirectory("mires-datadir-").FullName;
    }

    [TestCleanup]
    public void Cleanup()
    {
        if (_root == "") return;
        try
        {
            foreach (var entry in Directory.EnumerateFileSystemEntries(_root, "*", SearchOption.AllDirectories))
                if (Directory.Exists(entry)) File.SetUnixFileMode(entry, UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute);
            Directory.Delete(_root, recursive: true);
        }
        catch (IOException) { }
    }

    private static string Shell(string file, params string[] args)
    {
        var start = new ProcessStartInfo(file) { RedirectStandardOutput = true, UseShellExecute = false };
        foreach (var a in args) start.ArgumentList.Add(a);
        using var process = Process.Start(start)!;
        var output = process.StandardOutput.ReadToEnd().Trim();
        process.WaitForExit();
        return output;
    }

    [TestMethod]
    public void Init_creates_the_directory_group_owned_with_setgid_mode_2770()
    {
        var path = Path.Combine(_root, "data");

        var result = DataDirectory.Initialize(path, MyGroup, DataDirectory.CurrentPlatform);

        Assert.IsTrue(result.Ok, result.Error);
        Assert.AreEqual(Rwx2770, File.GetUnixFileMode(path));
        Assert.AreEqual(MyGroup, DataDirectory.GroupOf(path));
    }

    [TestMethod]
    public void Init_is_idempotent_and_repairs_a_wrong_mode()
    {
        var path = Path.Combine(_root, "data");
        Assert.IsTrue(DataDirectory.Initialize(path, MyGroup, DataDirectory.CurrentPlatform).Ok);
        File.SetUnixFileMode(path, UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute);

        var again = DataDirectory.Initialize(path, MyGroup, DataDirectory.CurrentPlatform);

        Assert.IsTrue(again.Ok, again.Error);
        Assert.AreEqual(Rwx2770, File.GetUnixFileMode(path));
    }

    [TestMethod]
    public void Init_with_a_missing_group_fails_naming_the_group_and_leaves_no_directory()
    {
        var path = Path.Combine(_root, "data");

        var result = DataDirectory.Initialize(path, "no-such-group-xyz", DataDirectory.CurrentPlatform);

        Assert.IsFalse(result.Ok);
        StringAssert.Contains(result.Error, "no-such-group-xyz");
        Assert.IsFalse(Directory.Exists(path));
    }
}

using Microsoft.Extensions.Logging.Abstractions;
using MiresSftpUploader.Core;
using MiresSftpUploader.Test.Support;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class DirectorySourceContractTests : SourceContract
{
    private readonly List<string> _roots = new();

    [TestCleanup]
    public void Cleanup()
    {
        foreach (var root in _roots) Directory.Delete(root, recursive: true);
    }

    protected override ISource CreateSource(IReadOnlyDictionary<string, byte[]> files)
    {
        var root = Directory.CreateTempSubdirectory("mires-source-").FullName;
        _roots.Add(root);
        foreach (var (path, data) in files)
        {
            var full = Path.Combine(root, path.Replace('/', Path.DirectorySeparatorChar));
            Directory.CreateDirectory(Path.GetDirectoryName(full)!);
            File.WriteAllBytes(full, data);
        }
        return new DirectorySource("contract", root);
    }

    protected override MoveTargetConfig CreateMoveTarget()
    {
        var root = Directory.CreateTempSubdirectory("mires-target-").FullName;
        _roots.Add(root);
        return new MoveTargetConfig { Action = MoveAction.Move, Path = root };
    }

    private static string TargetFile(MoveTargetConfig target, string relativePath) =>
        Path.Combine(target.Path!, relativePath.Replace('/', Path.DirectorySeparatorChar));

    protected override byte[]? ReadMoveTarget(MoveTargetConfig target, string relativePath) =>
        File.Exists(TargetFile(target, relativePath)) ? File.ReadAllBytes(TargetFile(target, relativePath)) : null;

    protected override void PutMoveTarget(MoveTargetConfig target, string relativePath, byte[] data)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(TargetFile(target, relativePath))!);
        File.WriteAllBytes(TargetFile(target, relativePath), data);
    }
}

[TestClass]
public sealed class DirectorySourceTests
{
    [TestMethod]
    public void A_cross_volume_move_copies_checks_the_length_renames_and_only_then_deletes_the_original()
    {
        var root = Directory.CreateTempSubdirectory("mires-move-").FullName;
        try
        {
            var from = Path.Combine(root, "a.bin");
            var to = Path.Combine(root, "target", "a.bin");
            Directory.CreateDirectory(Path.GetDirectoryName(to)!);
            File.WriteAllBytes(from, new byte[200_000]);
            var modified = new DateTime(2026, 3, 4, 5, 6, 7, DateTimeKind.Utc);
            File.SetLastWriteTimeUtc(from, modified);

            var result = DirectorySource.MoveByCopy(from, to);

            Assert.AreEqual(MoveStatus.Moved, result.Status, result.Detail);
            Assert.AreEqual(200_000, new FileInfo(to).Length);
            Assert.AreEqual(modified, File.GetLastWriteTimeUtc(to));
            Assert.IsFalse(File.Exists(from));
            Assert.AreEqual(1, Directory.GetFiles(Path.GetDirectoryName(to)!).Length, "no temporary copy is left behind");
        }
        finally
        {
            Directory.Delete(root, recursive: true);
        }
    }

    [TestMethod]
    public void A_cross_volume_move_onto_an_existing_file_keeps_both_and_leaves_no_temporary_copy()
    {
        var root = Directory.CreateTempSubdirectory("mires-move-").FullName;
        try
        {
            var from = Path.Combine(root, "a.bin");
            var to = Path.Combine(root, "t.bin");
            File.WriteAllBytes(from, [1, 2, 3]);
            File.WriteAllBytes(to, [9]);

            var result = DirectorySource.MoveByCopy(from, to);

            Assert.AreEqual(MoveStatus.TargetExists, result.Status);
            CollectionAssert.AreEqual(new byte[] { 9 }, File.ReadAllBytes(to));
            Assert.IsTrue(File.Exists(from));
            Assert.AreEqual(2, Directory.GetFiles(root).Length);
        }
        finally
        {
            Directory.Delete(root, recursive: true);
        }
    }

    [TestMethod]
    public async Task Symlinks_are_not_followed_and_empty_directories_are_not_created()
    {
        var root = Directory.CreateTempSubdirectory("mires-source-").FullName;
        var outside = Directory.CreateTempSubdirectory("mires-outside-").FullName;
        try
        {
            File.WriteAllText(Path.Combine(root, "real.txt"), "real");
            Directory.CreateDirectory(Path.Combine(root, "empty"));
            File.WriteAllText(Path.Combine(outside, "secret.txt"), "secret");
            try
            {
                File.CreateSymbolicLink(Path.Combine(root, "link.txt"), Path.Combine(outside, "secret.txt"));
                Directory.CreateSymbolicLink(Path.Combine(root, "linkdir"), outside);
            }
            catch (Exception ex) when (ex is UnauthorizedAccessException or IOException)
            {
                Assert.Inconclusive("Cannot create symlinks on this machine: " + ex.Message);
            }

            var remote = new FakeRemote();
            var engine = new Engine(remote, [new DirectorySource("scans", root)],
                new EngineSettings { RemoteRoot = "/upload" }, NullLogger<Engine>.Instance, TimeProvider.System);

            var result = await engine.RunAsync(new RunOptions(), new Progress<RunEvent>(), CancellationToken.None);

            Assert.AreEqual(0, result.ExitCode);
            CollectionAssert.AreEquivalent(
                new[] { "/upload/scans/real.txt", "/upload/scans/manifest.json" },
                remote.Files.Keys.ToArray());
            Assert.DoesNotContain("/upload/scans/empty", remote.Directories);
            Assert.DoesNotContain("/upload/scans/linkdir", remote.Directories);
        }
        finally
        {
            Directory.Delete(root, recursive: true);
            Directory.Delete(outside, recursive: true);
        }
    }
}

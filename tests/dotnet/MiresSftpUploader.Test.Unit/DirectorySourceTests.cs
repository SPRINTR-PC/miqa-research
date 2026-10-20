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
}

[TestClass]
public sealed class DirectorySourceTests
{
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

using Microsoft.Extensions.Logging.Abstractions;
using MiresSftpUploader.Core;
using MiresSftpUploader.Test.Support;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class ChangedDuringUploadTests
{
    private static readonly EngineSettings Settings = new()
    {
        RemoteRoot = "/upload",
        Retry = new RetrySettings { MaxAttempts = 3, BaseDelay = TimeSpan.Zero, MaxDelay = TimeSpan.Zero },
    };

    /// <summary>A Source whose first read of a file first runs <paramref name="duringFirstRead"/>, as if another program wrote to it.</summary>
    private sealed class WriterAtFirstRead(ISource inner, Action duringFirstRead) : ISource
    {
        public string Name => inner.Name;
        public string? RemotePath => inner.RemotePath;
        public IAsyncEnumerable<SourceFile> ListAsync(CancellationToken ct) => inner.ListAsync(ct);
        public Task<SourceFile?> StatAsync(string relativePath, CancellationToken ct) => inner.StatAsync(relativePath, ct);

        public async Task<Stream> OpenReadAsync(string relativePath, CancellationToken ct) =>
            new TriggerStream(await inner.OpenReadAsync(relativePath, ct), duringFirstRead);
    }

    private sealed class TriggerStream(Stream inner, Action trigger) : Stream
    {
        private bool _triggered;

        public override async ValueTask<int> ReadAsync(Memory<byte> buffer, CancellationToken ct = default)
        {
            var n = await inner.ReadAsync(buffer, ct);
            if (!_triggered)
            {
                _triggered = true;
                trigger();
            }
            return n;
        }

        public override int Read(byte[] buffer, int offset, int count) => inner.Read(buffer, offset, count);
        public override bool CanRead => true;
        public override bool CanSeek => false;
        public override bool CanWrite => false;
        public override long Length => inner.Length;
        public override long Position { get => inner.Position; set => throw new NotSupportedException(); }
        public override void Flush() { }
        public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
        public override void SetLength(long value) => throw new NotSupportedException();
        public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();
        protected override void Dispose(bool disposing)
        {
            if (disposing) inner.Dispose();
            base.Dispose(disposing);
        }
    }

    private static async Task<(RunResult Result, FakeRemote Remote)> RunWithChangeAsync(Action<string> change)
    {
        var directory = Directory.CreateTempSubdirectory("mires-changed-").FullName;
        try
        {
            var path = Path.Combine(directory, "slide.bin");
            await File.WriteAllBytesAsync(path, new byte[200_000]);
            var remote = new FakeRemote();
            var source = new WriterAtFirstRead(new DirectorySource("scans", directory), () => change(path));
            var engine = new Engine(remote, [source], Settings, NullLogger<Engine>.Instance, TimeProvider.System);

            var result = await engine.RunAsync(new RunOptions(), new Progress<RunEvent>(), CancellationToken.None);
            return (result, remote);
        }
        finally
        {
            Directory.Delete(directory, recursive: true);
        }
    }

    [TestMethod]
    public async Task File_that_grows_during_upload_fails_and_nothing_is_renamed()
    {
        var (result, remote) = await RunWithChangeAsync(path => File.AppendAllText(path, "more data"));

        Assert.AreEqual(ExitCodes.SomeFilesFailed, result.ExitCode);
        Assert.AreEqual(1, result.Count(FileOutcome.Failed));
        Assert.IsFalse(remote.Files.ContainsKey("/upload/scans/slide.bin"), "nothing may be renamed to the final name");
        Assert.IsFalse(remote.Files.Keys.Any(k => k.EndsWith(".part")), "the .part must be removed");
        StringAssert.Contains(remote.ReadText("/upload/scans/manifest.json"), "ChangedDuringUpload");
    }

    [TestMethod]
    public async Task File_rewritten_in_place_during_upload_fails_even_when_the_size_is_unchanged()
    {
        var (result, remote) = await RunWithChangeAsync(path =>
        {
            File.WriteAllBytes(path, new byte[200_000]);
            File.SetLastWriteTimeUtc(path, DateTime.UtcNow.AddHours(1));
        });

        Assert.AreEqual(ExitCodes.SomeFilesFailed, result.ExitCode);
        Assert.IsFalse(remote.Files.ContainsKey("/upload/scans/slide.bin"));
        StringAssert.Contains(remote.ReadText("/upload/scans/manifest.json"), "ChangedDuringUpload");
    }

    [TestMethod]
    public async Task File_that_does_not_change_still_succeeds()
    {
        var (result, remote) = await RunWithChangeAsync(_ => { });

        Assert.AreEqual(ExitCodes.Ok, result.ExitCode);
        Assert.IsTrue(remote.Files.ContainsKey("/upload/scans/slide.bin"));
    }
}

using System.Text.Json;
using Microsoft.Extensions.Logging.Abstractions;
using MiresSftpUploader.Core;
using MiresSftpUploader.Test.Support;

namespace MiresSftpUploader.Test.Unit;

/// <summary>
/// Opt-in volume tests (<c>--filter "TestCategory=Scale"</c>); excluded from the normal run. They watch memory, the number of
/// Upload State commits and the shape of the Manifest at sizes the unit tests never reach.
/// </summary>
[TestClass]
[TestCategory("Scale")]
[DoNotParallelize] // heap and commit counts are process-wide; other tests running alongside would be counted
public sealed class ScaleTests
{
    private const int FileCount = 20_000;

    private string _dir = "";

    [TestInitialize]
    public void Setup() => _dir = Directory.CreateTempSubdirectory("mires-scale-").FullName;

    [TestCleanup]
    public void Cleanup()
    {
        try { Directory.Delete(_dir, recursive: true); } catch (IOException) { }
    }

    private static FakeSource ManyTinyFiles(int count)
    {
        var source = new FakeSource("scans");
        for (var i = 0; i < count; i++) source.Add($"batch{i / 500:D3}/file{i:D6}.txt", $"content {i}");
        return source;
    }

    private Engine NewEngine(FakeRemote remote, FakeSource source) => new(remote, [source],
        new EngineSettings
        {
            RemoteRoot = "/upload",
            Destination = "sftp.example:22",
            Retry = new RetrySettings { MaxAttempts = 1, BaseDelay = TimeSpan.Zero, MaxDelay = TimeSpan.Zero },
            State = new StateSettings { Path = Path.Combine(_dir, "state.db") },
            Report = new ReportSettings { Directory = Path.Combine(_dir, "reports") },
        },
        NullLogger<Engine>.Instance, TimeProvider.System);

    [TestMethod]
    public async Task Twenty_thousand_tiny_files_keep_the_managed_heap_bounded()
    {
        var remote = new FakeRemote();
        var source = ManyTinyFiles(FileCount);
        var engine = NewEngine(remote, source);
        GC.Collect();
        var sink = new CountingSink();
        var baseline = GC.GetTotalMemory(forceFullCollection: true);
        long peak = baseline;
        using var stop = new CancellationTokenSource();
        var sampler = Task.Run(async () =>
        {
            while (!stop.IsCancellationRequested)
            {
                // Live bytes only: a forced collection leaves out garbage that merely has not been collected yet.
                peak = Math.Max(peak, GC.GetTotalMemory(forceFullCollection: true));
                await Task.Delay(20);
            }
        });

        await engine.RunAsync(new RunOptions(), new Progress<RunEvent>(), CancellationToken.None);
        await stop.CancelAsync();
        await sampler;

        GC.KeepAlive(remote);
        // Measured about 30 MB (roughly 1.5 KB per file: the Run's per-file outcomes, the plan and the Report). Linear in the number
        // of files, so the bound is generous and only trips on something per-file-sized going wrong, such as holding file content.
        var growthMb = (peak - baseline) / 1024.0 / 1024.0;
        Assert.IsTrue(growthMb < 100, $"live heap grew {growthMb:F1} MB for {FileCount} files");
    }

    [TestMethod]
    public async Task Twenty_thousand_tiny_files_upload_with_batched_state_writes_and_one_complete_Manifest()
    {
        var remote = new FakeRemote();
        var source = ManyTinyFiles(FileCount);
        var commitsBefore = UploadStateStore.CommitCount;

        var result = await NewEngine(remote, source).RunAsync(new RunOptions(), new Progress<RunEvent>(), CancellationToken.None);

        Assert.AreEqual(0, result.ExitCode);
        Assert.AreEqual(FileCount, result.Count(FileOutcome.Succeeded));
        using var manifest = JsonDocument.Parse(remote.ReadText("/upload/scans/manifest.json"));
        Assert.IsTrue(manifest.RootElement.GetProperty("complete").GetBoolean());
        Assert.AreEqual(FileCount, manifest.RootElement.GetProperty("members").GetArrayLength());

        // Every file writes a few statements; one transaction each would be at least FileCount commits.
        var commits = UploadStateStore.CommitCount - commitsBefore;
        Assert.IsTrue(commits < FileCount / 10, $"{commits} commits for {FileCount} files is not batched");
    }

    [TestMethod]
    public void A_million_node_Manifest_is_written_as_a_stream()
    {
        const int nodeCount = 1_000_000;
        var sink = new CountingSink();
        var baseline = GC.GetTotalMemory(forceFullCollection: true);
        long peak = baseline;
        IEnumerable<ManifestNode> Nodes()
        {
            for (var i = 0; i < nodeCount; i++)
            {
                // Live bytes while the writer is part-way through: a buffered Manifest would show up here.
                if (i % 100_000 == 0) peak = Math.Max(peak, GC.GetTotalMemory(forceFullCollection: true));
                yield return new ManifestFile($"batch{i / 500:D4}/file{i:D7}.txt", 13, "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef");
            }
        }
        var header = new ManifestHeader("scans", true, Guid.NewGuid(), DateTimeOffset.UnixEpoch, DateTimeOffset.UnixEpoch, "Run", "1.0", "host");
        

        ManifestWriter.Write(sink, header, [], [], Nodes);

        Assert.IsTrue(sink.Length > 200_000_000, $"only {sink.Length} bytes were written");
        var growthMb = (peak - baseline) / 1024.0 / 1024.0;
        Assert.IsTrue(growthMb < 20, $"live heap grew {growthMb:F1} MB while {sink.Length / 1048576} MB of Manifest went out");
    }

    [TestMethod]
    public async Task Loading_a_Sources_Upload_State_costs_a_known_number_of_bytes_per_file()
    {
        const int rows = 200_000;
        const int budgetBytesPerRow = 800; // measured: about 670 // see docs/scale.md: a Run holds the whole Source's state as a dictionary
        await using var store = UploadStateStore.Open(Path.Combine(_dir, "state.db"), TimeProvider.System);
        var run = Guid.NewGuid();
        await store.BeginRunAsync(run, DateTimeOffset.UtcNow, "Run", "Manual", "me");
        for (var i = 0; i < rows; i++)
            store.RecordSucceeded(run, new FileKey("sftp.example:22", "/upload/scans", "scans", $"batch{i / 500:D4}/file{i:D7}.txt"),
                13, 638_000_000_000_000_000 + i, new string('a', 64), DateTimeOffset.UtcNow, TimeSpan.Zero);
        await store.FlushAsync();

        var baseline = GC.GetTotalMemory(forceFullCollection: true);
        var loaded = store.LoadSource("sftp.example:22", "/upload/scans", "scans");
        var held = GC.GetTotalMemory(forceFullCollection: true) - baseline;

        Assert.AreEqual(rows, loaded.Count);
        var perRow = held / rows;
        Assert.IsTrue(perRow < budgetBytesPerRow, $"{perRow} bytes per file held, about {perRow} MB per 1,000,000 files");
    }

    private sealed class CountingSink : Stream
    {
        public long Total;
        public override bool CanRead => false;
        public override bool CanSeek => false;
        public override bool CanWrite => true;
        public override long Length => Total;
        public override long Position { get => Total; set => throw new NotSupportedException(); }
        public override void Flush() { }
        public override int Read(byte[] buffer, int offset, int count) => throw new NotSupportedException();
        public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
        public override void SetLength(long value) => throw new NotSupportedException();
        public override void Write(byte[] buffer, int offset, int count) => Total += count;
        public override void Write(ReadOnlySpan<byte> buffer) => Total += buffer.Length;
    }
}

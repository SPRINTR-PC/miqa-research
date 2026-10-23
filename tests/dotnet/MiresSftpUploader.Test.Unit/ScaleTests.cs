using System.Text.Json;
using Microsoft.Extensions.Logging.Abstractions;
using MiresSftpUploader.Core;
using MiresSftpUploader.Test.Support;

namespace MiresSftpUploader.Test.Unit;

/// <summary>
/// Opt-in volume tests (<c>--filter "TestCategory=Scale"</c>); excluded from the normal run. They drive the Engine with many
/// files and watch memory, the number of Upload State commits and the shape of the Manifest at sizes the unit tests never reach.
/// The commit count is the one thing they read from inside (<c>UploadStateStore.CommitCount</c>), because no public behaviour
/// tells how many transactions the Upload State used.
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

    private EngineSettings Settings() => new()
    {
        RemoteRoot = "/upload",
        Destination = "sftp.example:22",
        Retry = new RetrySettings { MaxAttempts = 1, BaseDelay = TimeSpan.Zero, MaxDelay = TimeSpan.Zero },
        State = new StateSettings { AccessGroup = TestAccessGroup.Name, Path = Path.Combine(_dir, "state.db") },
        Report = new ReportSettings { Directory = Path.Combine(_dir, "reports") },
    };

    private Engine NewEngine(IRemote remote, FakeSource source) =>
        new(remote, [source], Settings(), NullLogger<Engine>.Instance, TimeProvider.System);

    /// <summary>Samples the live heap (a forced collection leaves out garbage that merely has not been collected yet) until stopped.</summary>
    private sealed class HeapSampler : IDisposable
    {
        private readonly CancellationTokenSource _stop = new();
        private readonly Task _task;

        public long Baseline { get; }
        public long Peak { get; private set; }

        public HeapSampler()
        {
            Baseline = Peak = GC.GetTotalMemory(forceFullCollection: true);
            _task = Task.Run(async () =>
            {
                while (!_stop.IsCancellationRequested)
                {
                    Peak = Math.Max(Peak, GC.GetTotalMemory(forceFullCollection: true));
                    await Task.Delay(20);
                }
            });
        }

        public double GrowthMb => (Peak - Baseline) / 1024.0 / 1024.0;

        /// <summary>Stops sampling; the numbers stay readable.</summary>
        public void Stop()
        {
            if (_stopped) return;
            _stopped = true;
            _stop.Cancel();
            _task.Wait();
        }

        private bool _stopped;

        public void Dispose()
        {
            Stop();
            _stop.Dispose();
        }
    }

    [TestMethod]
    public async Task Twenty_thousand_tiny_files_keep_the_managed_heap_bounded()
    {
        var remote = new FakeRemote();
        var engine = NewEngine(remote, ManyTinyFiles(FileCount));
        GC.Collect();
        double growthMb;
        using (var heap = new HeapSampler())
        {
            await engine.RunAsync(new RunOptions(), new Progress<RunEvent>(), CancellationToken.None);
            heap.Stop();
            growthMb = heap.GrowthMb;
        }

        GC.KeepAlive(remote);
        // Measured about 30 MB (roughly 1.5 KB per file: the Run's per-file outcomes, the plan and the Report). Linear in the number
        // of files, so the bound is generous and only trips on something per-file-sized going wrong, such as holding file content.
        Assert.IsLessThan(100, growthMb, $"live heap grew {growthMb:F1} MB for {FileCount} files");
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
        Assert.IsLessThan(FileCount / 10, commits, $"{commits} commits for {FileCount} files is not batched");
    }

    /// <summary>
    /// Forwards to a <see cref="FakeRemote"/> but swallows the Manifest instead of keeping it, counting its bytes, and calls
    /// <paramref name="onConnection"/> with the number of each new connection and <paramref name="onManifest"/> when a Manifest is in
    /// place, so a test can tell when the Run was writing and uploading Manifests.
    /// </summary>
    private sealed class ManifestSwallowingRemote(FakeRemote inner, Action<int> onConnection, Action onManifest) : IRemote
    {
        private int _connections;
        public long ManifestBytes;
        internal void ManifestStored() => onManifest();

        public async Task<RemoteResult<IRemoteSession>> ConnectAsync(CancellationToken ct)
        {
            onConnection(Interlocked.Increment(ref _connections));
            var connect = await inner.ConnectAsync(ct);
            return connect.IsOk ? RemoteResult<IRemoteSession>.Ok(new Session(this, connect.Value!)) : connect;
        }

        private sealed class Session(ManifestSwallowingRemote owner, IRemoteSession session) : IRemoteSession
        {
            private static bool IsManifest(string path) => path.EndsWith("manifest.json.part", StringComparison.Ordinal);

            public async Task<RemoteResult> UploadAsync(Stream content, string path, CancellationToken ct)
            {
                if (!IsManifest(path)) return await session.UploadAsync(content, path, ct);
                var buffer = new byte[81920];
                int read;
                while ((read = await content.ReadAsync(buffer, ct)) > 0) owner.ManifestBytes += read;
                return RemoteResult.Ok;
            }

            public Task<RemoteResult> RenameAsync(string from, string to, bool overwrite, CancellationToken ct) =>
                IsManifest(from) ? Task.FromResult(Done()) : session.RenameAsync(from, to, overwrite, ct);

            private RemoteResult Done()
            {
                owner.ManifestStored();
                return RemoteResult.Ok;
            }

            public Task<RemoteResult> EnsureDirectoryAsync(string path, CancellationToken ct) => session.EnsureDirectoryAsync(path, ct);
            public Task<RemoteResult> DeleteAsync(string path, CancellationToken ct) => session.DeleteAsync(path, ct);
            public Task<RemoteResult<IReadOnlyList<string>>> ListAsync(string directory, CancellationToken ct) => session.ListAsync(directory, ct);
            public Task<RemoteResult<RemoteFileInfo>> StatAsync(string path, CancellationToken ct) => session.StatAsync(path, ct);
            public Task<RemoteResult> DownloadAsync(string path, Stream destination, CancellationToken ct) => session.DownloadAsync(path, destination, ct);
            public Task<RemoteResult<string>> RunCommandAsync(string command, CancellationToken ct) => session.RunCommandAsync(command, ct);
            public ValueTask DisposeAsync() => session.DisposeAsync();
        }
    }

    [TestMethod]
    public async Task The_Manifest_of_a_large_Source_is_written_as_a_stream()
    {
        const int files = 100_000;
        HeapSampler? heap = null;
        // Connections of a ReadWrite Run with one worker: the Markers, the worker, then the Manifests. The Report that follows
        // renders every file of the Run in memory, which is not what this test is about.
        var remote = new ManifestSwallowingRemote(new FakeRemote(), connection =>
        {
            if (connection == 3) heap = new HeapSampler();
        }, () => heap!.Stop());
        var settings = Settings() with { RemoteAccess = RemoteAccess.ReadWrite, MaxParallelUploads = 1 };

        var result = await new Engine(remote, [ManyTinyFiles(files)], settings, NullLogger<Engine>.Instance, TimeProvider.System)
            .RunAsync(new RunOptions(), new Progress<RunEvent>(), CancellationToken.None);
        heap!.Dispose();

        Assert.AreEqual(0, result.ExitCode, result.Reason);
        Assert.IsGreaterThan(15_000_000, remote.ManifestBytes, $"only {remote.ManifestBytes} bytes of Manifest went out");
        Assert.IsLessThan(20, heap.GrowthMb, $"live heap grew {heap.GrowthMb:F1} MB while {remote.ManifestBytes / 1048576} MB of Manifest was written and uploaded");
    }

    [TestMethod]
    public async Task An_incremental_Run_over_a_large_Source_holds_a_known_number_of_bytes_per_file()
    {
        const int files = 100_000;
        const int budgetBytesPerFile = 3_000; // a Run holds the Source's Upload State as a dictionary, its plan and its outcomes
        var remote = new FakeRemote();
        var engine = NewEngine(remote, ManyTinyFiles(files));
        await engine.RunAsync(new RunOptions(), new Progress<RunEvent>(), CancellationToken.None);
        remote.Inject(RemoteOperation.Upload, RemoteResult.Failed("must not upload"), times: 1_000_000, pathContains: "/batch");

        RunResult result;
        long perFile;
        using (var heap = new HeapSampler())
        {
            result = await engine.RunAsync(new RunOptions(), new Progress<RunEvent>(), CancellationToken.None);
            heap.Stop();
            perFile = (heap.Peak - heap.Baseline) / files;
        }

        Assert.AreEqual(files, result.Count(FileOutcome.Skipped), "unchanged files are skipped, not uploaded again");
        Assert.IsLessThan(budgetBytesPerFile, perFile, $"{perFile} bytes per file held, about {perFile} MB per 1,000,000 files");
    }
}

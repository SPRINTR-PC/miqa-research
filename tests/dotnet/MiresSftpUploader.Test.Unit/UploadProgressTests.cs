using System.Threading.Channels;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Time.Testing;
using MiresSftpUploader.Core;
using MiresSftpUploader.Test.Support;

namespace MiresSftpUploader.Test.Unit;

/// <summary>
/// The Engine's meter of acknowledged bytes: what the <see cref="UploadProgress"/> snapshots hold, driven by a fake clock
/// and a fake remote that reports as it consumes a throttled stream.
/// </summary>
[TestClass]
public sealed class UploadProgressTests
{
    private static readonly TimeSpan Tick = TimeSpan.FromMilliseconds(250);
    private static readonly TimeSpan Patience = TimeSpan.FromSeconds(10);

    private readonly FakeTimeProvider _time = new(new DateTimeOffset(2026, 6, 1, 12, 0, 0, TimeSpan.Zero));
    private readonly FakeRemote _remote = new() { UploadChunkSize = 100 };
    private readonly Events _events = new();
    private readonly Channel<long> _reached = Channel.CreateUnbounded<long>();
    private readonly Channel<bool> _go = Channel.CreateUnbounded<bool>();

    private static EngineSettings Settings(int attempts = 1, ArchiveConfig? archive = null, string? statePath = null) => new()
    {
        RemoteRoot = "/upload",
        Destination = "sftp.example:22",
        Retry = new RetrySettings { MaxAttempts = attempts, BaseDelay = TimeSpan.Zero, MaxDelay = TimeSpan.Zero },
        Archive = archive ?? new ArchiveConfig(),
        State = statePath is null ? new StateSettings() : new StateSettings { AccessGroup = TestAccessGroup.Name, Path = statePath },
    };

    private Task<RunResult> Run(EngineSettings settings, FakeSource source, RunOptions? options = null) =>
        new Engine(_remote, [source], settings, NullLogger<Engine>.Instance, _time)
            .RunAsync(options ?? new RunOptions(), _events, CancellationToken.None);

    /// <summary>Holds every reporting upload after each chunk until the test lets it go on.</summary>
    private void Throttle() => _remote.OnUploadChunk = async (_, total, _) =>
    {
        await _reached.Writer.WriteAsync(total);
        await _go.Reader.ReadAsync();
    };

    private async Task<long> NextChunk() => await _reached.Reader.ReadAsync().AsTask().WaitAsync(Patience);

    private void Release() => _go.Writer.TryWrite(true);

    private static byte[] Bytes(int count) => Enumerable.Range(0, count).Select(i => (byte)(i * 31 + 7)).ToArray();

    [TestMethod]
    public async Task A_snapshot_holds_acknowledged_bytes_total_and_the_Upload_Speed_once_two_samples_exist()
    {
        Throttle();
        var run = Run(Settings(), new FakeSource("scans").Add("big.bin", Bytes(1000)));

        Assert.AreEqual(100, await NextChunk());
        _time.Advance(Tick);
        var first = _events.Snapshots.Single().Files.Single();
        Assert.AreEqual("scans", first.Source);
        Assert.AreEqual("big.bin", first.RelativePath);
        Assert.AreEqual(100, first.BytesSent);
        Assert.AreEqual(1000, first.Total);
        Assert.IsNull(first.UploadSpeed, "no Upload Speed before 2 samples");
        Assert.IsNull(_events.Snapshots.Single().TotalUploadSpeed);

        Release();
        Assert.AreEqual(200, await NextChunk());
        _time.Advance(Tick);
        var second = _events.Snapshots.Last();
        Assert.AreEqual(200, second.Files.Single().BytesSent);
        Assert.AreEqual(400.0, second.Files.Single().UploadSpeed!.Value, 0.001, "100 bytes in 250 ms");
        Assert.AreEqual(400.0, second.TotalUploadSpeed!.Value, 0.001);

        await Finish(run);
        var last = _events.Snapshots.Last();
        Assert.IsEmpty(last.Files, "a last snapshot with no active files");
        Assert.IsNull(last.TotalUploadSpeed, "clears the total");
    }

    [TestMethod]
    public async Task Upload_Speed_is_smoothed_over_a_sliding_window()
    {
        Throttle();
        var run = Run(Settings(), new FakeSource("scans").Add("big.bin", Bytes(1000)));
        for (var chunk = 1; chunk <= 4; chunk++)
        {
            await NextChunk();
            _time.Advance(Tick);
            Release();
        }
        Assert.AreEqual(400.0, _events.Snapshots.Last().Files.Single().UploadSpeed!.Value, 0.001, "steady 100 bytes per tick");

        await NextChunk(); // 500 bytes are acknowledged; the upload then stalls for two ticks
        _time.Advance(Tick);
        _time.Advance(Tick);
        _time.Advance(Tick);

        // The window still holds the earlier samples, so the speed sags instead of dropping to 0 or jumping.
        var smoothed = _events.Snapshots.Last().Files.Single().UploadSpeed!.Value;
        Assert.IsLessThan(400.0, smoothed);
        Assert.IsGreaterThan(0.0, smoothed);

        // After more than the 3 s window without progress the speed is 0.
        for (var i = 0; i < 16; i++) _time.Advance(Tick);
        Assert.AreEqual(0.0, _events.Snapshots.Last().Files.Single().UploadSpeed!.Value, 0.001);

        await Finish(run);
    }

    [TestMethod]
    public async Task A_smaller_or_out_of_order_report_never_moves_a_file_backwards()
    {
        _remote.OnUploadChunk = async (_, total, progress) =>
        {
            if (total == 300) progress.Report(100);
            await _reached.Writer.WriteAsync(total);
            await _go.Reader.ReadAsync();
        };
        var run = Run(Settings(), new FakeSource("scans").Add("big.bin", Bytes(1000)));

        await NextChunk();
        Release();
        await NextChunk();
        Release();
        Assert.AreEqual(300, await NextChunk());
        _time.Advance(Tick);

        Assert.AreEqual(300, _events.Snapshots.Last().Files.Single().BytesSent);
        await Finish(run);
    }

    [TestMethod]
    public async Task A_retry_starts_the_file_again_at_0()
    {
        Throttle();
        _remote.CutNextUpload("big.bin");
        var run = Run(Settings(attempts: 2), new FakeSource("scans").Add("big.bin", Bytes(1000)));

        for (var chunk = 1; chunk <= 10; chunk++)
        {
            await NextChunk();
            if (chunk == 5) _time.Advance(Tick);
            Release();
        }
        Assert.AreEqual(500, _events.Snapshots.Last().Files.Single().BytesSent, "the first attempt got to 500 when sampled");

        Assert.AreEqual(100, await NextChunk(), "the second attempt starts at the beginning");
        _time.Advance(Tick);
        Assert.AreEqual(100, _events.Snapshots.Last().Files.Single().BytesSent);
        Assert.IsTrue(_events.Snapshots.Any(s => s.Files.Count == 0), "the failed attempt cleared its progress");

        await Finish(run);
    }

    [TestMethod]
    public async Task An_uploaded_Archive_reports_like_a_file_with_the_size_of_the_zip()
    {
        _remote.OnUploadChunk = async (_, total, _) =>
        {
            if (total > 100) return;
            await _reached.Writer.WriteAsync(total);
            await _go.Reader.ReadAsync();
        };
        var archive = new ArchiveConfig
        {
            Rules = [new ArchiveRuleConfig { Name = "bins", Pattern = @"\.bin$", Grouping = ArchiveGrouping.PerRule, ArchiveName = "all.zip", MinFiles = 1 }],
            StagingPath = Directory.CreateTempSubdirectory("mires-progress-").FullName,
        };
        var run = Run(Settings(archive: archive), new FakeSource("scans").Add("a.bin", Bytes(1000)));

        Assert.AreEqual(100, await NextChunk());
        _time.Advance(Tick);
        var file = _events.Snapshots.Last().Files.Single();
        Assert.AreEqual("all.zip", file.RelativePath);
        Assert.AreEqual(100, file.BytesSent);

        Release();
        var result = await run.WaitAsync(Patience);
        Assert.AreEqual(0, result.ExitCode);
        Assert.AreEqual(_remote.Files["/upload/scans/all.zip"].Length, file.Total);
        Assert.IsEmpty(_events.Snapshots.Last().Files);
    }

    [TestMethod]
    public async Task A_Dry_Run_emits_no_UploadProgress()
    {
        var run = Run(Settings(), new FakeSource("scans").Add("big.bin", Bytes(1000)), new RunOptions { DryRun = true });
        await run.WaitAsync(Patience);
        _time.Advance(TimeSpan.FromSeconds(2));

        Assert.IsEmpty(_events.Snapshots);
    }

    [TestMethod]
    public async Task A_Run_without_a_throttle_still_ends_with_a_clean_final_state()
    {
        var result = await Run(Settings(), new FakeSource("scans").Add("a.txt", "alpha")).WaitAsync(Patience);

        Assert.AreEqual(0, result.ExitCode);
        Assert.IsTrue(_events.Snapshots.All(s => s.Files.Count == 0 || s.Files.All(f => f.BytesSent <= f.Total)));
    }

    private async Task Finish(Task<RunResult> run)
    {
        _remote.OnUploadChunk = null;
        for (var i = 0; i < 64; i++) Release();
        // Chunks already waiting for a release still report to the channel; drain it so nothing blocks.
        _ = Task.Run(async () => { await foreach (var _ in _reached.Reader.ReadAllAsync()) { } });
        var result = await run.WaitAsync(Patience);
        Assert.AreEqual(0, result.ExitCode);
    }

    private sealed class Events : IProgress<RunEvent>
    {
        private readonly object _gate = new();
        private readonly List<UploadProgress> _snapshots = [];

        public IReadOnlyList<UploadProgress> Snapshots
        {
            get { lock (_gate) return _snapshots.ToArray(); }
        }

        public void Report(RunEvent value)
        {
            if (value is UploadProgress snapshot) lock (_gate) _snapshots.Add(snapshot);
        }
    }
}

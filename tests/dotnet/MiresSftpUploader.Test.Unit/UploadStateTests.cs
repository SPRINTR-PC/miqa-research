using Microsoft.Extensions.Logging.Abstractions;
using MiresSftpUploader.Core;
using MiresSftpUploader.Test.Support;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class UploadStateTests
{
    private string _dir = "";

    [TestInitialize]
    public void Setup() => _dir = Directory.CreateTempSubdirectory("mires-state-").FullName;

    [TestCleanup]
    public void Cleanup()
    {
        try { Directory.Delete(_dir, recursive: true); } catch (IOException) { }
    }

    private string DbPath => Path.Combine(_dir, "state.db");

    private EngineSettings Settings(Func<StateSettings, StateSettings>? state = null) => new()
    {
        RemoteRoot = "/upload",
        Destination = "sftp.example:22",
        Retry = new RetrySettings { MaxAttempts = 2, BaseDelay = TimeSpan.Zero, MaxDelay = TimeSpan.Zero },
        State = (state ?? (s => s))(new StateSettings { Path = DbPath }),
    };

    private static Engine NewEngine(EngineSettings settings, TimeProvider time, FakeRemote remote, params ISource[] sources) =>
        new(remote, sources, settings, NullLogger<Engine>.Instance, time);

    private static Task<RunResult> Run(Engine engine, RunOptions? options = null) =>
        engine.RunAsync(options ?? new RunOptions(), new Progress<RunEvent>(), CancellationToken.None);

    [TestMethod]
    public async Task Second_run_skips_unchanged_files_without_reading_them()
    {
        var remote = new FakeRemote();
        var source = new FakeSource("scans").Add("a.txt", "alpha").Add("b.txt", "beta");
        var engine = NewEngine(Settings(), TimeProvider.System, remote, source);
        await Run(engine);
        var readsAfterFirst = source.OpenCount;

        var second = await Run(engine);

        Assert.AreEqual(0, second.ExitCode);
        Assert.AreEqual(2, second.Count(FileOutcome.Skipped));
        Assert.AreEqual(readsAfterFirst, source.OpenCount);
    }
}

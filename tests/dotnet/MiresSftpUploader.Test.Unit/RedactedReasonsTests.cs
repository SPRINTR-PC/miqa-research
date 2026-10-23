using Microsoft.Extensions.Logging.Abstractions;
using MiresSftpUploader.Core;
using MiresSftpUploader.Test.Support;

namespace MiresSftpUploader.Test.Unit;

/// <summary>Secrets are removed from everything a Run stores or shows, not only from log lines.</summary>
[TestClass]
public sealed class RedactedReasonsTests
{
    private const string Secret = "hunter2-very-secret";

    private string _dir = "";

    [TestInitialize]
    public void Setup() => _dir = Directory.CreateTempSubdirectory("mires-redact-").FullName;

    [TestCleanup]
    public void Cleanup()
    {
        try { Directory.Delete(_dir, recursive: true); } catch (IOException) { }
    }

    private EngineSettings Settings() => new()
    {
        RemoteRoot = "/upload",
        Destination = "sftp.example:22",
        RemoteAccess = RemoteAccess.ReadWrite,
        Redactor = Redactor.From(Secrets.FromEnvironment(new Dictionary<string, string?> { ["MIRES_SFTP_PASSWORD"] = Secret })),
        Retry = new RetrySettings { MaxAttempts = 1, BaseDelay = TimeSpan.Zero, MaxDelay = TimeSpan.Zero },
        State = new StateSettings { AccessGroup = TestAccessGroup.Name, Path = Path.Combine(_dir, "state.db") },
        Report = new ReportSettings { Directory = Path.Combine(_dir, "reports") },
    };

    private sealed class Events : IProgress<RunEvent>
    {
        public List<RunEvent> All { get; } = [];
        public void Report(RunEvent value) { lock (All) All.Add(value); }
    }

    [TestMethod]
    public async Task A_failure_reason_with_a_Secret_in_it_is_masked_everywhere_it_is_stored_or_shown()
    {
        var remote = new FakeRemote();
        remote.Inject(RemoteOperation.Upload, RemoteResult.Failed($"auth failed, password {Secret} was refused"), times: 9, pathContains: "a.txt");
        var settings = Settings();
        var events = new Events();

        var result = await new Engine(remote, [new FakeSource("scans").Add("a.txt", "a")], settings, NullLogger<Engine>.Instance, TimeProvider.System)
            .RunAsync(new RunOptions(), events, CancellationToken.None);

        Assert.AreEqual(ExitCodes.SomeFilesFailed, result.ExitCode);
        var shown = string.Join("\n", events.All.OfType<FileOutcomeChanged>().Select(e => e.Reason));
        StringAssert.Contains(shown, "password *** was refused");
        var stored = new RunHistory(settings.State, TimeProvider.System).GetRun(result.RunId)!.Files.Single().Reason;
        StringAssert.Contains(stored, "password *** was refused");
        Assert.DoesNotContain(Secret, remote.ReadText("/upload/scans/manifest.json"), "the Manifest lists the reason of a failure");
        // Upload State (database and journal files) and Report, byte for byte.
        foreach (var file in Directory.EnumerateFiles(_dir, "*", SearchOption.AllDirectories).Where(f => !f.EndsWith(".lock")))
            Assert.DoesNotContain(Secret, System.Text.Encoding.Latin1.GetString(File.ReadAllBytes(file)), file);
    }

    [TestMethod]
    public async Task A_run_level_reason_with_a_Secret_in_it_is_masked()
    {
        var remote = new FakeRemote();
        remote.Inject(RemoteOperation.Connect, RemoteResult.Failed($"cannot log in with {Secret}"), times: 9);
        var settings = Settings() with { RemoteAccess = RemoteAccess.WriteOnly };

        var result = await new Engine(remote, [new FakeSource("scans").Add("a.txt", "a")], settings, NullLogger<Engine>.Instance, TimeProvider.System)
            .RunAsync(new RunOptions(), new Events(), CancellationToken.None);

        Assert.AreEqual(ExitCodes.ConnectFailed, result.ExitCode);
        Assert.DoesNotContain(Secret, result.Reason);
        StringAssert.Contains(result.Reason, "cannot log in with ***");
    }
}

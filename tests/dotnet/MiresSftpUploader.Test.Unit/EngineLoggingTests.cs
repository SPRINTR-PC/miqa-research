using Microsoft.Extensions.Logging;
using MiresSftpUploader.Core;
using MiresSftpUploader.Test.Support;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class EngineLoggingTests : ConfigurationTestBase
{
    private const string Password = "hunter2-very-secret";

    private static readonly EngineSettings FastSettings = new()
    {
        RemoteRoot = "/upload",
        Retry = new RetrySettings { MaxAttempts = 2, BaseDelay = TimeSpan.Zero, MaxDelay = TimeSpan.Zero },
    };

    private (Engine Engine, CapturingLoggerProvider Log) NewEngine(FakeRemote remote, FakeSource source)
    {
        var secrets = Create(ValidMachine().ToJsonString(), env: new() { ["MIRES_SFTP_PASSWORD"] = Password }).LoadSecrets();
        var log = new CapturingLoggerProvider();
        var factory = LoggerFactory.Create(b => b.SetMinimumLevel(LogLevel.Trace).AddProvider(new RedactingLoggerProvider(log, Redactor.From(secrets))));
        return (new Engine(remote, [source], FastSettings, new Logger<Engine>(factory), TimeProvider.System), log);
    }

    [TestMethod]
    public async Task Each_file_outcome_is_logged_and_the_Run_ends_with_a_summary()
    {
        var remote = new FakeRemote();
        remote.Inject(RemoteOperation.Upload, RemoteResult.Failed("disk full"), times: 2, pathContains: "bad.txt");
        var (engine, log) = NewEngine(remote, new FakeSource("scans").Add("ok.txt", "a").Add("bad.txt", "b"));

        await engine.RunAsync(new RunOptions(), new Progress<RunEvent>(), CancellationToken.None);

        var entries = log.Entries;
        Assert.IsTrue(entries.Any(e => e.Level == LogLevel.Information && e.Message.Contains("scans/ok.txt") && e.Message.Contains("Succeeded")), "Succeeded file at Info");
        Assert.IsTrue(entries.Any(e => e.Level == LogLevel.Error && e.Message.Contains("scans/bad.txt") && e.Message.Contains("disk full")), "Failed file at Error");
        Assert.IsTrue(entries.Any(e => e.Level == LogLevel.Warning && e.Message.Contains("attempt 1/2")), "Retry at Warning");
        var summary = entries.Last(e => e.Level == LogLevel.Information);
        StringAssert.Contains(summary.Message, "Succeeded 1");
        StringAssert.Contains(summary.Message, "Failed 1");
        StringAssert.Contains(summary.Message, "exit code 1");
    }

    [TestMethod]
    public async Task A_Secret_in_a_remote_failure_reason_never_appears_in_any_log()
    {
        var remote = new FakeRemote();
        remote.Inject(RemoteOperation.Upload, RemoteResult.Failed($"auth rejected for {Password}"), times: 100);
        var (engine, log) = NewEngine(remote, new FakeSource("scans").Add("a.txt", "a"));

        await engine.RunAsync(new RunOptions(), new Progress<RunEvent>(), CancellationToken.None);

        Assert.IsNotEmpty(log.Entries);
        foreach (var entry in log.Entries)
            Assert.DoesNotContain(Password, entry.Message);
        Assert.IsTrue(log.Entries.Any(e => e.Message.Contains("auth rejected for ***")));
    }
}

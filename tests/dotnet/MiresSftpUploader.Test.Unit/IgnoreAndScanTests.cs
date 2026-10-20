using Microsoft.Extensions.Logging.Abstractions;
using MiresSftpUploader.Core;
using MiresSftpUploader.Test.Support;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class IgnoreAndScanTests
{
    private static readonly DateTimeOffset Now = new(2026, 6, 1, 12, 0, 0, TimeSpan.Zero);

    private sealed class FixedClock(DateTimeOffset now) : TimeProvider
    {
        public override DateTimeOffset GetUtcNow() => now;
    }

    private static EngineSettings Settings() => new()
    {
        RemoteRoot = "/upload",
        Retry = new RetrySettings { MaxAttempts = 1, BaseDelay = TimeSpan.Zero, MaxDelay = TimeSpan.Zero },
    };

    private static async Task<(RunResult Result, List<FileOutcomeChanged> Events)> RunAsync(
        FakeRemote remote, EngineSettings settings, RunOptions? options, params ISource[] sources)
    {
        var events = new List<FileOutcomeChanged>();
        var engine = new Engine(remote, sources, settings, NullLogger<Engine>.Instance, new FixedClock(Now));
        var result = await engine.RunAsync(options ?? new RunOptions(), new SyncProgress(events), CancellationToken.None);
        return (result, events);
    }

    private static string? ReasonOf(List<FileOutcomeChanged> events, string path, FileOutcome outcome) =>
        events.Last(e => e.RelativePath == path && e.Outcome == outcome).Reason;

    [TestMethod]
    public async Task Built_in_junk_files_are_Ignored_at_any_depth_and_never_uploaded()
    {
        var remote = new FakeRemote();
        var source = new FakeSource("scans")
            .Add("keep.txt", "k").Add(".DS_Store", "x").Add("sub/Thumbs.db", "x")
            .Add("sub/desktop.ini", "x").Add("sub/._keep.txt", "x");

        var (result, _) = await RunAsync(remote, Settings(), null, source);

        Assert.AreEqual(0, result.ExitCode);
        Assert.AreEqual(1, result.Count(FileOutcome.Succeeded));
        Assert.AreEqual(4, result.Count(FileOutcome.Ignored));
        CollectionAssert.AreEquivalent(
            new[] { "/upload/scans/keep.txt", "/upload/scans/manifest.json" }, remote.Files.Keys.ToArray());
    }

    [TestMethod]
    public async Task Exact_files_and_case_insensitive_patterns_over_the_forward_slash_path_are_Ignored()
    {
        var remote = new FakeRemote();
        var source = new FakeSource("scans")
            .Add("keep.txt", "k").Add("notes/draft.txt", "x").Add("tmp/a.TMP", "x").Add("deep/dir/b.tmp", "x");
        var settings = Settings() with
        {
            Ignore = new IgnoreConfig { Files = ["notes/draft.txt"], Patterns = [@"\.tmp$", @"^deep/dir/"] },
        };

        var (result, events) = await RunAsync(remote, settings, null, source);

        Assert.AreEqual(1, result.Count(FileOutcome.Succeeded));
        Assert.AreEqual(3, result.Count(FileOutcome.Ignored));
        Assert.IsFalse(remote.Files.Keys.Any(k => k.Contains("draft") || k.Contains("tmp")));
        Assert.AreEqual("Ignore:Files", ReasonOf(events, "notes/draft.txt", FileOutcome.Ignored));
    }

    [TestMethod]
    public async Task UseDefaults_false_uploads_the_built_in_junk_files()
    {
        var remote = new FakeRemote();
        var source = new FakeSource("scans").Add(".DS_Store", "x");
        var settings = Settings() with { Ignore = new IgnoreConfig { UseDefaults = false } };

        var (result, _) = await RunAsync(remote, settings, null, source);

        Assert.AreEqual(1, result.Count(FileOutcome.Succeeded));
        Assert.AreEqual(0, result.Count(FileOutcome.Ignored));
    }

    [TestMethod]
    public async Task A_Source_adds_its_own_rules_without_affecting_other_Sources()
    {
        var remote = new FakeRemote();
        var a = new FakeSource("a").Add("x.log", "x").Add("y.txt", "y");
        var b = new FakeSource("b").Add("x.log", "x");
        var settings = Settings() with
        {
            Ignore = new IgnoreConfig { Files = ["y.txt"] },
            SourceConfigs = [new SourceConfig { Name = "A", Ignore = new SourceIgnoreConfig { Patterns = [@"\.log$"] } }],
        };

        var (_, _) = await RunAsync(remote, settings, null, a, b);

        Assert.IsFalse(remote.Files.ContainsKey("/upload/a/x.log"));
        Assert.IsFalse(remote.Files.ContainsKey("/upload/a/y.txt"));
        Assert.IsTrue(remote.Files.ContainsKey("/upload/b/x.log"));
    }

    [TestMethod]
    public async Task A_pattern_that_times_out_does_not_ignore_the_file_and_raises_a_warning()
    {
        var remote = new FakeRemote();
        var source = new FakeSource("scans").Add(new string('a', 40) + "!", "x");
        var settings = Settings() with { Ignore = new IgnoreConfig { Patterns = ["^(a+)+$"] } };
        var warnings = new List<RunWarning>();
        var engine = new Engine(remote, [source], settings, NullLogger<Engine>.Instance, new FixedClock(Now));

        var result = await engine.RunAsync(new RunOptions(), new WarningProgress(warnings), CancellationToken.None);

        Assert.AreEqual(1, result.Count(FileOutcome.Succeeded));
        Assert.HasCount(1, warnings);
    }

    private sealed class WarningProgress(List<RunWarning> sink) : IProgress<RunEvent>
    {
        public void Report(RunEvent value)
        {
            if (value is RunWarning w) lock (sink) sink.Add(w);
        }
    }

    private sealed class SyncProgress(List<FileOutcomeChanged> sink) : IProgress<RunEvent>
    {
        public void Report(RunEvent value)
        {
            if (value is FileOutcomeChanged c) lock (sink) sink.Add(c);
        }
    }
}

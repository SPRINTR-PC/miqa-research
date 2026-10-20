using System.Diagnostics;
using Microsoft.Extensions.Logging.Abstractions;
using MiresSftpUploader.Core;
using MiresSftpUploader.Test.Support;

namespace MiresSftpUploader.Test.Unit;

/// <summary>What a Run does with the Data Directory at its start.</summary>
[TestClass]
[System.Runtime.Versioning.UnsupportedOSPlatform("windows")]
public sealed class DataDirectoryRunTests
{
    private string _root = "";

    [TestInitialize]
    public void Setup()
    {
        if (OperatingSystem.IsWindows()) Assert.Inconclusive("Unix permission semantics.");
        _root = Directory.CreateTempSubdirectory("mires-run-").FullName;
    }

    [TestCleanup]
    public void Cleanup()
    {
        try
        {
            foreach (var d in Directory.EnumerateDirectories(_root, "*", SearchOption.AllDirectories).Append(_root))
                File.SetUnixFileMode(d, UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute);
            Directory.Delete(_root, recursive: true);
        }
        catch (IOException) { }
    }

    /// <summary>Progress&lt;T&gt; posts to the thread pool, which loses ordering; the order of events matters here.</summary>
    private sealed class SyncProgress(List<RunEvent> events) : IProgress<RunEvent>
    {
        public void Report(RunEvent value) { lock (events) events.Add(value); }
    }

    private static string MyGroup()
    {
        var start = new ProcessStartInfo("id", "-gn") { RedirectStandardOutput = true, UseShellExecute = false };
        using var process = Process.Start(start)!;
        var group = process.StandardOutput.ReadToEnd().Trim();
        process.WaitForExit();
        return group;
    }

    private static (RunResult Result, List<RunEvent> Events) Run(string dataDirectory, string? group = null)
    {
        var settings = new EngineSettings
        {
            Destination = "sftp.example:22",
            State = new StateSettings { Path = DataDirectory.DatabasePath(dataDirectory), AccessGroup = group },
        };
        var engine = new Engine(new FakeRemote(), [new FakeSource("scans").Add("a.txt", "alpha")], settings,
            NullLogger<Engine>.Instance, TimeProvider.System);
        var events = new List<RunEvent>();
        var result = engine.RunAsync(new RunOptions(), new SyncProgress(events), CancellationToken.None).GetAwaiter().GetResult();
        return (result, events);
    }

    [TestMethod]
    public void Missing_directory_that_cannot_be_created_exits_2_naming_path_account_and_fix()
    {
        if (Environment.UserName == "root") Assert.Inconclusive("Root can create anything.");
        File.SetUnixFileMode(_root, UnixFileMode.UserRead | UnixFileMode.UserExecute);
        var dataDirectory = Path.Combine(_root, "data");

        var (result, _) = Run(dataDirectory, MyGroup());

        Assert.AreEqual(ExitCodes.ConfigurationError, result.ExitCode);
        StringAssert.Contains(result.Reason, dataDirectory);
        StringAssert.Contains(result.Reason, Environment.UserName);
        StringAssert.Contains(result.Reason, "--init-data-dir");
        Assert.IsFalse(Directory.Exists(dataDirectory), "no silent fallback or partial creation");
    }

    [TestMethod]
    public void Existing_directory_that_is_not_writable_exits_2()
    {
        if (Environment.UserName == "root") Assert.Inconclusive("Root can write anywhere.");
        File.SetUnixFileMode(_root, UnixFileMode.UserRead | UnixFileMode.UserExecute);

        var (result, _) = Run(_root);

        Assert.AreEqual(ExitCodes.ConfigurationError, result.ExitCode);
        StringAssert.Contains(result.Reason, "not writable");
    }

    [TestMethod]
    public void Missing_directory_is_set_up_implicitly_when_rights_allow()
    {
        var dataDirectory = Path.Combine(_root, "data");

        var (result, _) = Run(dataDirectory, MyGroup());

        Assert.AreEqual(ExitCodes.Ok, result.ExitCode, result.Reason);
        Assert.AreEqual((UnixFileMode)Convert.ToInt32("2770", 8), File.GetUnixFileMode(dataDirectory));
        Assert.IsTrue(File.Exists(DataDirectory.DatabasePath(dataDirectory)));
    }

    [TestMethod]
    public void Access_check_is_reported_as_an_event_at_each_Run_start()
    {
        var (_, events) = Run(_root);

        var check = events.OfType<DataDirectoryChecked>().Single();
        Assert.IsTrue(check.Access.Writable);
        Assert.AreEqual(_root, check.Access.Path);
        Assert.IsInstanceOfType<RunStarted>(events[0]);
        Assert.IsLessThan(events.FindIndex(e => e is FileOutcomeChanged), events.IndexOf(check));
    }
}

using Microsoft.Extensions.Logging;
using MiresSftpUploader.Core;
using MiresSftpUploader.Logging;
using NLog.Targets;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class AppLoggingTests
{
    private static readonly IReadOnlyDictionary<string, string> NoSection = new Dictionary<string, string>();
    private string _dir = "";

    [TestInitialize]
    public void Setup() => _dir = Path.Combine(Path.GetTempPath(), "mires-log-" + Guid.NewGuid().ToString("N"));

    [TestCleanup]
    public void Cleanup()
    {
        try { Directory.Delete(_dir, true); } catch (IOException) { }
    }

    private string ReadAllLogs() =>
        string.Concat(Directory.GetFiles(_dir, "*", SearchOption.AllDirectories).Select(File.ReadAllText));

    private AppLogging Start(LoggingConfig? config = null, bool headless = false, IReadOnlyDictionary<string, string>? section = null, Redactor? redactor = null) =>
        AppLogging.Start(config ?? new LoggingConfig { Directory = _dir }, section ?? NoSection, headless, redactor ?? Redactor.None, defaultDirectory: Path.Combine(_dir, "default"));

    [TestMethod]
    public void Logs_at_or_above_the_configured_level_go_to_a_file_in_the_configured_directory()
    {
        using (var logging = Start(new LoggingConfig { Directory = _dir, Level = LogLevelSetting.Info }))
        {
            var log = logging.LoggerFactory.CreateLogger("Test");
            log.LogDebug("too chatty");
            log.LogInformation("file one done");
            log.LogError("file two failed");
        }

        var text = ReadAllLogs();
        StringAssert.Contains(text, "file one done");
        StringAssert.Contains(text, "file two failed");
        Assert.DoesNotContain("too chatty", text);
        Assert.IsTrue(Directory.GetFiles(_dir).Length > 0);
    }

    [TestMethod]
    public void File_only_logging_has_no_console_and_no_pane_target_even_when_the_console_is_switched_on()
    {
        using var logging = AppLogging.Start(new LoggingConfig { Directory = _dir, Console = true }, NoSection, headless: true, Redactor.None, _dir, fileOnly: true);

        var targets = logging.LogFactory.Configuration!.AllTargets;
        Assert.AreEqual(1, targets.Count);
        Assert.IsInstanceOfType<FileTarget>(targets[0]);
        Assert.IsNull(logging.Ui);
    }

    [TestMethod]
    public void File_only_logging_strips_console_targets_from_a_user_supplied_NLog_section()
    {
        var custom = Path.Combine(_dir, "custom.log");
        var section = new Dictionary<string, string>
        {
            ["targets:file:type"] = "File",
            ["targets:file:fileName"] = custom,
            ["targets:console:type"] = "Console",
            ["targets:colored:type"] = "ColoredConsole",
            ["rules:0:logger"] = "*",
            ["rules:0:minLevel"] = "Info",
            ["rules:0:writeTo"] = "file,console,colored",
        };

        using (var logging = AppLogging.Start(new LoggingConfig { Directory = _dir }, section, headless: true, Redactor.None, _dir, fileOnly: true))
        {
            var targets = logging.LogFactory.Configuration!.AllTargets;
            Assert.IsEmpty(targets.OfType<ConsoleTarget>().ToList());
            Assert.IsEmpty(targets.OfType<ColoredConsoleTarget>().ToList());
            Assert.IsEmpty(logging.LogFactory.Configuration!.LoggingRules.SelectMany(r => r.Targets).Where(t => t is ConsoleTarget or ColoredConsoleTarget).ToList());
            logging.LoggerFactory.CreateLogger("Test").LogWarning("to the file only");
        }

        StringAssert.Contains(File.ReadAllText(custom), "to the file only");
    }

    [TestMethod]
    public void Log_directory_defaults_to_the_given_default_when_none_is_configured()
    {
        using (var logging = Start(new LoggingConfig()))
            logging.LoggerFactory.CreateLogger("Test").LogInformation("hello");

        Assert.IsTrue(Directory.GetFiles(Path.Combine(_dir, "default")).Length > 0);
    }

    [TestMethod]
    public void The_file_target_archives_daily_and_keeps_the_configured_number_of_days()
    {
        using var logging = Start(new LoggingConfig { Directory = _dir, RetainDays = 14 });

        var file = logging.LogFactory.Configuration!.AllTargets.OfType<FileTarget>().Single();
        Assert.AreEqual(NLog.Targets.FileArchivePeriod.Day, file.ArchiveEvery);
        Assert.AreEqual(14, file.MaxArchiveDays);
    }

    [TestMethod]
    public void Headless_writes_to_the_console_on_stderr_and_has_no_UI_target()
    {
        using var logging = Start(headless: true);

        var console = logging.LogFactory.Configuration!.AllTargets.OfType<ConsoleTarget>().Single();
        Assert.IsTrue(console.StdErr.FixedValue);
        Assert.IsNull(logging.Ui);
    }

    [TestMethod]
    public void The_UI_run_has_a_UI_target_and_no_console_unless_asked_for()
    {
        using (var logging = Start())
        {
            Assert.IsNotNull(logging.Ui);
            Assert.IsEmpty(logging.LogFactory.Configuration!.AllTargets.OfType<ConsoleTarget>().ToList());
        }
        using (var logging = Start(new LoggingConfig { Directory = _dir, Console = true }))
            Assert.HasCount(1, logging.LogFactory.Configuration!.AllTargets.OfType<ConsoleTarget>().ToList());
    }

    [TestMethod]
    public void Log_events_reach_the_UI_target_subscribers_including_Debug_below_the_file_level()
    {
        var received = new List<LogEntry>();
        using (var logging = Start(new LoggingConfig { Directory = _dir, Level = LogLevelSetting.Info }))
        {
            logging.Ui!.LogReceived += received.Add;
            var log = logging.LoggerFactory.CreateLogger("Test");
            log.LogDebug("sftp stat /x");
            log.LogWarning("retry {N}", 2);
        }

        CollectionAssert.AreEqual(new[] { "sftp stat /x", "retry 2" }, received.Select(e => e.Message).ToArray());
        CollectionAssert.AreEqual(new[] { LogLevel.Debug, LogLevel.Warning }, received.Select(e => e.Level).ToArray());
    }

    [TestMethod]
    public void An_NLog_section_replaces_the_generated_configuration()
    {
        var custom = Path.Combine(_dir, "custom.log");
        var section = new Dictionary<string, string>
        {
            ["targets:file:type"] = "File",
            ["targets:file:fileName"] = custom,
            ["targets:file:layout"] = "${level}|${message}",
            ["rules:0:logger"] = "*",
            ["rules:0:minLevel"] = "Warn",
            ["rules:0:writeTo"] = "file",
        };

        using (var logging = Start(new LoggingConfig { Directory = Path.Combine(_dir, "generated") }, section: section))
        {
            var log = logging.LoggerFactory.CreateLogger("Test");
            log.LogInformation("below the custom rule");
            log.LogWarning("retrying");
        }

        Assert.AreEqual("Warn|retrying", File.ReadAllText(custom).Trim());
        Assert.IsFalse(Directory.Exists(Path.Combine(_dir, "generated")), "the generated configuration must not be used");
    }

    [TestMethod]
    public void A_Secret_never_appears_in_the_log_file()
    {
        const string password = "hunter2-very-secret";
        var redactor = RedactorFor(password);

        using (var logging = Start(redactor: redactor))
        {
            var log = logging.LoggerFactory.CreateLogger("Test");
            log.LogWarning("login failed for {Password}", password);
            log.LogError(new IOException($"bad credentials {password}"), "connect failed");
        }

        var text = ReadAllLogs();
        StringAssert.Contains(text, "login failed for ***");
        StringAssert.Contains(text, "bad credentials ***");
        Assert.DoesNotContain(password, text);
    }

    private static Redactor RedactorFor(string password)
    {
        var locations = new ConfigurationLocations("/none", "/none", new Dictionary<string, string?> { ["MIRES_SFTP_PASSWORD"] = password });
        return Redactor.From(new Core.Configuration(locations).LoadSecrets());
    }
}

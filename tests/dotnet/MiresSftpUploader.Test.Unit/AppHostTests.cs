using System.Text.Json.Nodes;
using Microsoft.Extensions.Logging;
using MiresSftpUploader.Core;
using MiresSftpUploader.Logging;
using MiresSftpUploader.Test.Support;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class AppHostTests : ConfigurationTestBase
{
    private AppHost NewHost(JsonObject machine, AppLogging? logging, out Configuration configuration)
    {
        File.WriteAllText(MachinePath, machine.ToJsonString());
        configuration = new Configuration(new ConfigurationLocations(MachinePath, UserPath, new Dictionary<string, string?>()));
        var runtime = new UploaderRuntime(configuration, new StaticRemoteFactory(new FakeRemote()), Microsoft.Extensions.Logging.Abstractions.NullLoggerFactory.Instance, TimeProvider.System);
        return new AppHost(configuration, runtime, logging);
    }

    private AppLogging StartLogging() =>
        AppLogging.Start(new LoggingConfig { Directory = Path.Combine(Dir, "logs") }, new Dictionary<string, string>(), headless: false, Redactor.None, Dir);

    [TestMethod]
    public void The_window_starts_in_the_configured_theme_with_the_Sources_from_the_configuration()
    {
        var machine = ValidMachine();
        machine["Ui"] = new JsonObject { ["Theme"] = "Light" };

        var window = NewHost(machine, null, out _).CreateMainWindowViewModel(a => a());

        Assert.AreEqual(UiTheme.Light, window.Theme);
        CollectionAssert.AreEqual(new[] { "alpha" }, window.Upload.Sources.Select(s => s.Name).ToArray());
        Assert.AreEqual("sftp.example.org:22", window.Upload.Destination);
    }

    [TestMethod]
    public void The_log_pane_is_attached_to_the_log_target_with_the_configured_level()
    {
        var machine = ValidMachine();
        machine["Ui"] = new JsonObject { ["LogLevel"] = "Warn" };
        using var logging = StartLogging();
        var window = NewHost(machine, logging, out _).CreateMainWindowViewModel(a => a());

        var log = logging.LoggerFactory.CreateLogger("Test");
        log.LogInformation("routine");
        log.LogError("trouble");

        Assert.IsTrue(window.HasLog);
        Assert.AreEqual(LogLevel.Warning, window.Log!.MinimumLevel);
        CollectionAssert.AreEqual(new[] { "trouble" }, window.Log.Entries.Select(e => e.Message).ToArray());
    }

    [TestMethod]
    public void Without_logging_there_is_no_log_pane()
    {
        var window = NewHost(ValidMachine(), null, out _).CreateMainWindowViewModel(a => a());

        Assert.IsFalse(window.HasLog);
    }

    [TestMethod]
    public void An_invalid_configuration_opens_the_window_with_the_problems_listed()
    {
        var window = NewHost(new JsonObject(), null, out _).CreateMainWindowViewModel(a => a());

        Assert.IsTrue(window.Upload.HasProblems);
        StringAssert.Contains(window.Upload.Problems, "Sftp:Host");
        Assert.AreEqual(UiTheme.Dark, window.Theme, "dark when nothing says otherwise");
    }

    [TestMethod]
    public void Toggling_the_theme_saves_it_to_User_Overrides()
    {
        var window = NewHost(ValidMachine(), null, out var configuration).CreateMainWindowViewModel(a => a());

        window.ToggleThemeCommand.Execute().Subscribe();

        Assert.AreEqual(UiTheme.Light, configuration.Load().Config!.Ui.Theme);
    }
}

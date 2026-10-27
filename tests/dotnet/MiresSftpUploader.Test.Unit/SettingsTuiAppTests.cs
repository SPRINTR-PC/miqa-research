using Microsoft.Extensions.Logging.Abstractions;
using MiresSftpUploader.Core;
using MiresSftpUploader.SettingsTui;
using Terminal.Gui.App;
using Terminal.Gui.Drivers;
using Terminal.Gui.Input;
using Terminal.Gui.Testing;

namespace MiresSftpUploader.Test.Unit;

/// <summary>The entry point of the Settings TUI takes the application, so a test injects Terminal.Gui's headless driver and runs the real loop.</summary>
[TestClass]
public sealed class SettingsTuiAppTests : ConfigurationTestBase
{
    private static IApplication HeadlessApp()
    {
        var app = Application.Create();
        app.Init(DriverRegistry.Names.ANSI);
        app.Driver!.SetScreenSize(100, 32);
        return app;
    }

    [TestMethod]
    [Timeout(30000)]
    public void Run_on_an_injected_application_returns_0_after_Ctrl_Q()
    {
        var cfg = Create(ValidMachine().ToJsonString());
        using var app = HeadlessApp();
        app.Invoke(() => app.InjectKey(Key.Q.WithCtrl));

        var exit = SettingsTuiApp.Run(cfg, new CliOptions(), NullLoggerFactory.Instance, app, new FakeTuiDialogs());

        Assert.AreEqual(ExitCodes.Ok, exit);
    }

    [TestMethod]
    [Timeout(30000)]
    public void Esc_does_not_quit_the_running_application()
    {
        var cfg = Create(ValidMachine().ToJsonString());
        using var app = HeadlessApp();
        var dialogs = new FakeTuiDialogs();
        app.Invoke(() => app.InjectKey(Key.Esc));
        app.Invoke(() => app.InjectKey(Key.F4));
        app.Invoke(() => app.InjectKey(Key.Q.WithCtrl));

        SettingsTuiApp.Run(cfg, new CliOptions(), NullLoggerFactory.Instance, app, dialogs);

        Assert.HasCount(1, dialogs.IssueLists, "F4 after Esc must still reach the window");
    }

    [TestMethod]
    [Timeout(30000)]
    public void Run_saves_nothing_on_its_own()
    {
        var cfg = Create(ValidMachine().ToJsonString());
        var before = File.ReadAllText(MachinePath);
        using var app = HeadlessApp();
        app.Invoke(() => app.InjectKey(Key.Q.WithCtrl));

        SettingsTuiApp.Run(cfg, new CliOptions(), NullLoggerFactory.Instance, app, new FakeTuiDialogs());

        Assert.AreEqual(before, File.ReadAllText(MachinePath));
        Assert.IsFalse(File.Exists(UserPath));
    }
}

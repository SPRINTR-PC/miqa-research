using MiresSftpUploader.Core;
using MiresSftpUploader.SettingsTui;
using MiresSftpUploader.ViewModels;
using Terminal.Gui.Input;
using Terminal.Gui.Testing;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class SettingsTuiDataDirectoryPageTests : SettingsTuiTestBase
{
    private const string FixCommand = "sudo mkdir -p /srv/mires-data && sudo chgrp mires /srv/mires-data && sudo chmod 2770 /srv/mires-data";

    private static readonly int PageIndex = PageCatalog.Titles.ToList().IndexOf("Data Directory");

    private static DataDirectoryAccess Healthy(string path) =>
        new(path, true, true, "alice", "mires", 2048, 5L * 1024 * 1024 * 1024, false, "", null);

    private static DataDirectoryAccess Broken(string path) =>
        new(path, true, false, "alice", "mires", 0, 0, false, FixCommand, "The Data Directory is not writable by alice.");

    private SettingsTuiHarness StartOnPage(Func<string, DataDirectoryAccess> check, Func<string, long>? free = null)
    {
        var cfg = Create(ValidMachine().ToJsonString());
        var page = new SettingsPageViewModel(cfg, check, free ?? (_ => long.MaxValue));
        var tui = Start(cfg, page: page);
        tui.Window.PageIndex = PageIndex;
        return tui;
    }

    [TestMethod]
    public void A_healthy_Data_Directory_shows_status_free_space_and_database_size()
    {
        var tui = StartOnPage(Healthy);

        StringAssert.Contains(tui.Screen, "Writable by alice (group mires)");
        StringAssert.Contains(tui.Screen, "5.0 GiB free");
        StringAssert.Contains(tui.Row("Upload State database")!, "2.0 KiB");
        Assert.IsFalse(tui.Lines[0].Contains("cannot be used"));
        Assert.IsTrue(tui.Shows("Recheck"));
    }

    [TestMethod]
    public void A_problem_shows_its_text_and_the_whole_fix_command_and_turns_the_header_red()
    {
        var tui = StartOnPage(Broken);

        StringAssert.Contains(tui.Screen, "not writable by alice.");
        var inner = string.Concat(tui.Lines.Select(l => l.Split('│').Length > 2 ? l.Split('│')[^2] : "")).Replace(" ", "");
        StringAssert.Contains(inner, FixCommand.Replace(" ", ""), tui.Screen);
        StringAssert.Contains(tui.Lines[0], "Data Directory cannot be used");
    }

    [TestMethod]
    public void Recheck_reads_the_Data_Directory_again()
    {
        var broken = true;
        var tui = StartOnPage(p => broken ? Broken(p) : Healthy(p));
        StringAssert.Contains(tui.Lines[0], "cannot be used");

        broken = false;
        tui.Press(Key.Enter);
        tui.TabTo("Data Directory");
        tui.Press(Key.Tab);
        Assert.IsInstanceOfType<Terminal.Gui.Views.Button>(tui.Focused, tui.FocusPath);
        tui.Press(Key.Enter);

        Assert.IsFalse(tui.Lines[0].Contains("cannot be used"), tui.Screen);
        StringAssert.Contains(tui.Screen, "Writable by alice");
        Assert.IsFalse(tui.Shows("not writable by alice."));
    }

    [TestMethod]
    public void Network_share_split_state_and_staging_warnings_are_shown()
    {
        var tui = StartOnPage(p => Healthy(p) with { OnNetworkShare = true }, _ => 10);
        tui.Press(Key.Enter);
        tui.TabTo("Data Directory");
        tui.Press(Key.End);
        tui.Type("/elsewhere-state");

        StringAssert.Contains(tui.Screen, "network share");
        StringAssert.Contains(tui.Screen, "not the shared Data Directory");
        StringAssert.Contains(tui.Screen, "has 10 B free");
    }

    [TestMethod]
    public void The_data_dir_option_sets_the_checked_Data_Directory_and_locks_the_field()
    {
        var cfg = Create(ValidMachine().ToJsonString());
        var cli = CliOptions.Parse(["--configure", "--data-dir", "/srv/from-cli"]).Options!;
        var checkedPaths = new List<string>();
        var page = new SettingsPageViewModel(cfg, p => { checkedPaths.Add(p); return Healthy(p); }, _ => long.MaxValue, cli);

        var tui = Start(cfg, page: page);
        tui.Window.PageIndex = PageIndex;

        Assert.AreEqual("/srv/from-cli", page.DataDirectoryPath);
        Assert.AreEqual("/srv/from-cli", checkedPaths[0]);
        Assert.IsTrue(page.Field("State:Path").IsLocked);
        StringAssert.Contains(tui.Screen, "/srv/from-cli");
        Assert.IsFalse(page.HasChanges);
    }

    [TestMethod]
    [Timeout(30000)]
    public void SettingsTuiApp_applies_the_data_dir_option()
    {
        var cfg = Create(ValidMachine().ToJsonString());
        var cli = CliOptions.Parse(["--configure", "--data-dir", "/srv/from-cli"]).Options!;
        using var app = Terminal.Gui.App.Application.Create();
        app.Init(Terminal.Gui.Drivers.DriverRegistry.Names.ANSI);
        app.Driver!.SetScreenSize(100, 32);
        var seen = "";
        for (var i = 0; i < PageIndex; i++) app.Invoke(() => app.InjectKey(Key.PageDown.WithCtrl));
        app.Invoke(() => { app.LayoutAndDraw(true); seen = app.Driver!.ToString() ?? ""; });
        app.Invoke(() => app.InjectKey(Key.Q.WithCtrl));

        SettingsTuiApp.Run(cfg, cli, Microsoft.Extensions.Logging.Abstractions.NullLoggerFactory.Instance, app, new FakeTuiDialogs());

        StringAssert.Contains(seen, "/srv/from-cli");
    }

    [TestMethod]
    public void A_long_fix_command_is_shown_whole_at_the_minimum_size()
    {
        var path = "/srv/" + string.Join("/", Enumerable.Repeat("a-rather-long-name", 3));
        var command = $"sudo mkdir -p {path} && sudo chgrp mires {path} && sudo chmod 2770 {path}";
        var cfg = Create(ValidMachine().ToJsonString());
        var page = new SettingsPageViewModel(cfg, p => new DataDirectoryAccess(p, true, false, "alice", "mires", 0, 0, false, command, "The Data Directory is not writable by alice."), _ => long.MaxValue);
        var tui = Start(cfg, 80, 24, page: page);
        tui.Window.PageIndex = PageIndex;

        var inner = string.Concat(tui.Lines.Select(l => l.Split('│').Length > 2 ? l.Split('│')[^2] : "")).Replace(" ", "");
        StringAssert.Contains(inner, command.Replace(" ", ""), tui.Screen);
    }
}

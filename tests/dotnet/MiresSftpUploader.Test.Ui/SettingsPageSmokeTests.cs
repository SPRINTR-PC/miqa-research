using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Avalonia.Controls;
using Avalonia.Headless.XUnit;
using Avalonia.Threading;
using Avalonia.VisualTree;
using MiresSftpUploader.Core;
using MiresSftpUploader.Test.Support;
using MiresSftpUploader.ViewModels;
using MiresSftpUploader.Views;
using Xunit;

namespace MiresSftpUploader.Test.Ui;

public sealed class SettingsPageSmokeTests : IDisposable
{
    private readonly string _dir = Path.Combine(Path.GetTempPath(), "mires-ui-settings-" + Guid.NewGuid().ToString("N"));

    public void Dispose()
    {
        try { Directory.Delete(_dir, true); } catch (IOException) { }
    }

    private (MainWindow Window, MainWindowViewModel Vm, SettingsPageViewModel Settings) Create(Dictionary<string, string?>? env = null, UiTheme theme = UiTheme.Dark)
    {
        var install = Path.Combine(_dir, "install");
        Directory.CreateDirectory(install);
        var data = Path.Combine(_dir, "data");
        Directory.CreateDirectory(data);
        File.WriteAllText(Path.Combine(install, "appsettings.json"), $$"""
            {
              "Sftp": { "Host": "sftp.example.org", "Username": "u", "HostKeyFingerprint": "abc" },
              "Sources": [ { "Name": "alpha", "Type": "Directory", "Path": {{System.Text.Json.JsonSerializer.Serialize(data)}} } ]
            }
            """);
        var configuration = new Configuration(new ConfigurationLocations(Path.Combine(install, "appsettings.json"), Path.Combine(_dir, "user", "appsettings.user.json"), env ?? []));
        var settings = new SettingsPageViewModel(configuration,
            path => new DataDirectoryAccess(path, true, true, "alice", "mires-uploader", 0, 1L << 33, false, "", null), _ => long.MaxValue);
        var upload = new UploadPageViewModel(new FakeUploaderRuntime(new AppConfig(), new FakeRunEngine()), a => a());
        var vm = new MainWindowViewModel(upload, null, theme, _ => null, settings: settings);
        var window = new MainWindow { DataContext = vm };
        window.Show();
        vm.ShowSettingsCommand.Execute().Subscribe();
        Layout(window);
        return (window, vm, settings);
    }

    private static void Layout(Window window)
    {
        Dispatcher.UIThread.RunJobs();
        window.UpdateLayout();
    }

    private static TextBox TextBoxFor(Control root, string key) =>
        root.GetVisualDescendants().OfType<TextBox>().First(t => t.DataContext is SettingFieldViewModel f && f.Key == key && f.IsText);

    [AvaloniaTheory]
    [InlineData(UiTheme.Dark)]
    [InlineData(UiTheme.Light)]
    public void The_Settings_page_constructs_in_both_themes(UiTheme theme)
    {
        var (window, _, _) = Create(theme: theme);

        Assert.True(window.GetVisualDescendants().OfType<SettingsView>().Single().IsEffectivelyVisible);
        Assert.Equal("sftp.example.org", TextBoxFor(window, "Sftp:Host").Text);
    }

    [AvaloniaFact]
    public void A_Locked_Setting_is_shown_but_not_editable()
    {
        var (window, _, _) = Create(env: new() { ["MIRES_Sftp__Host"] = "env.example.org" });

        var host = TextBoxFor(window, "Sftp:Host");
        var username = TextBoxFor(window, "Sftp:Username");

        Assert.Equal("env.example.org", host.Text);
        Assert.False(host.IsEffectivelyEnabled);
        Assert.True(username.IsEffectivelyEnabled);
    }

    [AvaloniaFact]
    public void A_validation_error_disables_Save_and_shows_inline()
    {
        var (window, _, settings) = Create();
        var save = window.GetVisualDescendants().OfType<Button>().First(b => b.Name == "SaveButton");
        Assert.False(save.IsEffectivelyEnabled, "nothing to save yet");

        TextBoxFor(window, "Sftp:Port").Text = "0";
        Layout(window);

        Assert.False(save.IsEffectivelyEnabled);
        Assert.Contains("out of range", settings.Field("Sftp:Port").Error);
        Assert.Contains(window.GetVisualDescendants().OfType<TextBlock>(), t => t.Text is { } s && s.Contains("out of range") && t.IsEffectivelyVisible);

        TextBoxFor(window, "Sftp:Port").Text = "2222";
        Layout(window);

        Assert.True(save.IsEffectivelyEnabled);
    }

    [AvaloniaFact]
    public void Secrets_show_set_or_not_set_and_have_no_input()
    {
        var (window, _, _) = Create(env: new() { ["MIRES_SFTP_PASSWORD"] = "hunter2-secret" });

        string TextOf(string name) => window.GetVisualDescendants().OfType<TextBlock>().First(t => t.Name == name).Text!;

        Assert.Equal("set", TextOf("SftpPasswordStatusText"));
        Assert.Equal("not set", TextOf("SftpKeyPassphraseStatusText"));
        Assert.DoesNotContain(window.GetVisualDescendants().OfType<TextBox>(), t => t.Text is { } s && s.Contains("hunter2"));
    }

    [AvaloniaFact]
    public void The_Source_fields_adapt_to_the_Type()
    {
        var (window, _, settings) = Create();
        var row = settings.Sources[0];
        var pathBox = window.GetVisualDescendants().OfType<TextBox>().First(t => ReferenceEquals(t.DataContext, row) && t.Text == row.Path);
        var endpointBox = window.GetVisualDescendants().OfType<TextBox>().First(t => ReferenceEquals(t.DataContext, row) && t.Text == row.Endpoint && t != pathBox);
        Assert.True(pathBox.IsEffectivelyVisible);
        Assert.False(endpointBox.IsEffectivelyVisible);

        row.TypeName = "S3";
        Layout(window);

        Assert.False(pathBox.IsEffectivelyVisible);
        Assert.True(endpointBox.IsEffectivelyVisible);
    }

    [AvaloniaFact]
    public void The_Host_Key_Fingerprint_is_read_only_until_confirmed()
    {
        var (window, _, _) = Create();

        Assert.False(TextBoxFor(window, "Sftp:HostKeyFingerprint").IsEffectivelyEnabled);
        Assert.Contains(window.GetVisualDescendants().OfType<Button>(), b => b.Content as string == "Change…" && b.IsEffectivelyVisible);
    }

    [AvaloniaFact]
    public void An_unusable_Data_Directory_shows_a_banner_and_disables_Start()
    {
        var (window, vm, settings) = Create();
        Assert.False(window.GetVisualDescendants().OfType<Border>().First(b => b.Name == "DataDirectoryBanner").IsVisible);

        vm.Upload.BlockedReason = "not writable";
        vm.ShowUploadCommand.Execute().Subscribe();
        Layout(window);

        Assert.True(window.GetVisualDescendants().OfType<Border>().First(b => b.Name == "BlockedBanner").IsEffectivelyVisible);
        Assert.False(window.GetVisualDescendants().OfType<Button>().First(b => b.Name == "StartButton").IsEffectivelyEnabled);
        Assert.NotNull(settings);
    }
}

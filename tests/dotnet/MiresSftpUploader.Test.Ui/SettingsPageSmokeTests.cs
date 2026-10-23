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
        var configuration = new Configuration(new ConfigurationLocations(Path.Combine(install, "appsettings.json"), Path.Combine(_dir, "user", "appsettings.user.json"), env ?? [],
            Path.Combine(_dir, "user", "secrets.db"), new FixedIdentity("machine-1", "alice")));
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
    public void Browsing_for_a_Source_fills_its_Directory_path_box()
    {
        var (window, _, settings) = Create();
        var picked = Path.Combine(_dir, "picked");
        settings.PickFolder = () => System.Threading.Tasks.Task.FromResult<string?>(picked);
        var box = window.GetVisualDescendants().OfType<TextBox>().First(t => t.DataContext is SourceEditorViewModel && t.Text == settings.Sources[0].Path);

        settings.Sources[0].BrowseCommand.Execute().Subscribe();
        Layout(window);

        Assert.Equal(picked, settings.Sources[0].Path);
        Assert.Equal(picked, box.Text);
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

    private sealed record FixedIdentity(string? MachineId, string Account) : IMachineIdentity;

    private static TextBlock StatusOf(Control root, SecretEntryViewModel entry) =>
        root.GetVisualDescendants().OfType<TextBlock>().First(t => t.Name == "SecretStatusText" && ReferenceEquals(t.DataContext, entry));

    private static TextBox InputOf(Control root, SecretEntryViewModel entry) =>
        root.GetVisualDescendants().OfType<TextBox>().First(t => t.Name == "SecretInput" && ReferenceEquals(t.DataContext, entry));

    private static Button ButtonOf(Control root, SecretEntryViewModel entry, string name) =>
        root.GetVisualDescendants().OfType<Button>().First(b => b.Name == name && ReferenceEquals(b.DataContext, entry));

    [AvaloniaFact]
    public void Secrets_show_where_they_come_from_and_the_inputs_are_masked_and_empty()
    {
        var (window, _, settings) = Create(env: new() { ["MIRES_SFTP_PASSWORD"] = "hunter2-secret" });

        Assert.Equal("environment variable", StatusOf(window, settings.SftpPassword).Text);
        Assert.Equal("not set", StatusOf(window, settings.SftpKeyPassphrase).Text);
        foreach (var entry in new[] { settings.SftpPassword, settings.SftpKeyPassphrase })
        {
            var box = InputOf(window, entry);
            Assert.NotEqual('\0', box.PasswordChar);
            Assert.True(string.IsNullOrEmpty(box.Text));
        }
        Assert.False(InputOf(window, settings.SftpPassword).IsEffectivelyEnabled);
        Assert.True(InputOf(window, settings.SftpKeyPassphrase).IsEffectivelyEnabled);
        Assert.DoesNotContain(window.GetVisualDescendants().OfType<TextBox>(), t => t.Text is { } s && s.Contains("hunter2"));
    }

    [AvaloniaFact]
    public void A_typed_Secret_is_saved_with_the_button_and_the_box_empties()
    {
        var (window, _, settings) = Create();
        var entry = settings.SftpKeyPassphrase;
        var box = InputOf(window, entry);
        var save = ButtonOf(window, entry, "SecretSaveButton");
        Assert.False(save.IsEffectivelyEnabled);

        box.Text = "phrase-typed";
        Layout(window);
        Assert.True(save.IsEffectivelyEnabled);
        entry.SaveCommand.Execute().Subscribe();
        Layout(window);

        Assert.Equal("stored", StatusOf(window, entry).Text);
        Assert.True(string.IsNullOrEmpty(box.Text));
        Assert.True(ButtonOf(window, entry, "SecretClearButton").IsEffectivelyEnabled);
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

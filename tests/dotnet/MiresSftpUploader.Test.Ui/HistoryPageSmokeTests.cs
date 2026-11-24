using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Headless.XUnit;
using Avalonia.Styling;
using Avalonia.Threading;
using Avalonia.VisualTree;
using MiresSftpUploader.Core;
using MiresSftpUploader.Test.Support;
using MiresSftpUploader.ViewModels;
using MiresSftpUploader.Views;
using Xunit;

namespace MiresSftpUploader.Test.Ui;

public class HistoryPageSmokeTests
{
    private static Dictionary<string, int> Counts(int ok = 0, int failed = 0, int skipped = 0, int movedAway = 0) =>
        new[] { ("Succeeded", ok), ("Failed", failed), ("Skipped", skipped), ("MovedAway", movedAway) }
            .Where(c => c.Item2 > 0).ToDictionary(c => c.Item1, c => c.Item2);

    private static RunFileOutcome File(string path, string outcome, string? reason = null) => new("wsi", path, outcome, 10, 1, reason);

    private static (MainWindow Window, MainWindowViewModel Vm, FakeRunHistory History) Create(UiTheme theme = UiTheme.Dark, Action<FakeRunHistory>? seed = null)
    {
        var history = new FakeRunHistory();
        history.Add(status: "Running", exitCode: null, startedBy: "sofia", counts: Counts(ok: 2));
        history.Add(status: "Running", exitCode: null, startedBy: "anna", counts: Counts(ok: 1));
        history.Add(exitCode: 1, startedBy: "anna", counts: Counts(ok: 1, failed: 1, skipped: 1, movedAway: 1),
            files: [File("a", "Succeeded"), File("b", "Failed", "RemoteDenied"), File("c", "Skipped", "TooRecent"), File("d", "MovedAway")]);
        history.Add(status: "Abandoned", exitCode: null, startedBy: "bo", counts: Counts(failed: 1));
        seed?.Invoke(history);
        var upload = new UploadPageViewModel(new FakeUploaderRuntime(new AppConfig(), new FakeRunEngine()), a => a());
        var page = new HistoryPageViewModel(history, "anna", a => a(), _ => Task.FromResult<string?>(null));
        var vm = new MainWindowViewModel(upload, null, theme, _ => null, page);
        return (new MainWindow { DataContext = vm }, vm, history);
    }

    private static T Find<T>(Control root, string name) where T : Control =>
        root.GetVisualDescendants().OfType<T>().First(c => c.Name == name);

    [AvaloniaTheory]
    [InlineData(UiTheme.Dark)]
    [InlineData(UiTheme.Light)]
    public void The_History_page_constructs_and_shows_in_both_themes(UiTheme theme)
    {
        var (window, vm, _) = Create(theme);
        window.Show();

        vm.ShowHistoryCommand.Execute().Subscribe();
        vm.History!.Selected = vm.History.Runs[2];
        Dispatcher.UIThread.RunJobs();
        window.UpdateLayout();

        Assert.Equal(theme == UiTheme.Dark ? ThemeVariant.Dark : ThemeVariant.Light, Application.Current!.RequestedThemeVariant);
        Assert.True(Find<Control>(window, "HistoryPage").IsVisible);
        Assert.False(Find<Control>(window, "UploadPage").IsVisible);
        Assert.Equal(4, Find<ListBox>(window, "RunList").ItemCount);
        var texts = window.GetVisualDescendants().OfType<TextBlock>().Select(t => t.Text).ToList();
        Assert.Contains("Moved away", texts);
        Assert.Contains("Skipped (incl. 1 Too Recent)", texts);
    }

    [AvaloniaFact]
    public void Cancel_and_Retry_differ_for_own_and_other_users_Runs_in_the_detail_pane()
    {
        var (window, vm, _) = Create();
        window.Show();
        vm.ShowHistoryCommand.Execute().Subscribe();
        var page = vm.History!;

        void Select(int index)
        {
            page.Selected = page.Runs[index];
            Dispatcher.UIThread.RunJobs();
            window.UpdateLayout();
        }

        Select(0); // sofia's live Run
        Assert.Equal("Request cancel (sofia's Run)", Find<Button>(window, "HistoryCancelButton").Content);
        Assert.True(Find<Button>(window, "HistoryCancelButton").IsEffectivelyEnabled);
        Assert.False(Find<Button>(window, "HistoryRetryButton").IsEffectivelyEnabled);
        Assert.True(Find<Control>(window, "LiveBanner").IsVisible);

        Select(1); // own live Run
        Assert.Equal("Cancel", Find<Button>(window, "HistoryCancelButton").Content);
        Assert.True(Find<Button>(window, "HistoryCancelButton").IsEffectivelyEnabled);
        Assert.False(Find<Control>(window, "LiveBanner").IsVisible);

        page.Selected!.CancelCommand.Execute().Subscribe();
        Dispatcher.UIThread.RunJobs();
        Assert.False(Find<Button>(window, "HistoryCancelButton").IsEffectivelyEnabled);
        Assert.True(Find<Control>(window, "CancelRequestedBanner").IsVisible);

        Select(2); // own finished Run with failures
        Assert.False(Find<Button>(window, "HistoryCancelButton").IsVisible);
        Assert.True(Find<Button>(window, "HistoryRetryButton").IsEffectivelyEnabled);

        Select(3); // Abandoned Run
        Assert.True(Find<Control>(window, "AbandonedBanner").IsVisible);
        Assert.True(Find<Button>(window, "HistoryRetryButton").IsEffectivelyEnabled);
    }

    [AvaloniaFact]
    public void The_header_shows_what_a_Run_uploaded_but_not_for_a_Dry_Run_or_an_empty_upload()
    {
        Guid uploaded = default, dryRun = default, empty = default;
        var (window, vm, _) = Create(seed: h =>
        {
            uploaded = h.Add(counts: Counts(ok: 1), files: [File("a", "Succeeded")]).Summary.RunId;
            dryRun = h.Add(mode: "DryRun", counts: Counts(ok: 1), files: [File("a", "Succeeded")]).Summary.RunId;
            empty = h.Add(counts: Counts(skipped: 1), files: [File("a", "Skipped", "unchanged")]).Summary.RunId;
        });
        window.Show();
        vm.ShowHistoryCommand.Execute().Subscribe();
        var page = vm.History!;

        TextBlock Total(Guid id)
        {
            page.Selected = page.Runs.Single(r => r.RunId == id);
            Dispatcher.UIThread.RunJobs();
            window.UpdateLayout();
            return Find<TextBlock>(window, "HistoryUploadedTotal");
        }

        Assert.True(Total(uploaded).IsVisible);
        Assert.Equal("Uploaded 10 bytes", Total(uploaded).Text);
        Assert.False(Total(dryRun).IsVisible);
        Assert.False(Total(empty).IsVisible);
    }
}

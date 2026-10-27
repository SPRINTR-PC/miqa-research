using System;
using System.Collections.Generic;
using System.ComponentModel;
using MiresSftpUploader.ViewModels;
using Terminal.Gui.ViewBase;
using Terminal.Gui.Views;

namespace MiresSftpUploader.SettingsTui.Pages;

/// <summary>
/// The Data Directory page: the Data Directory field, then what the check found (path, status, free space, Upload State database size), the
/// network-share, split-state and Staging Area warnings, the problem and the full fix command in a read-only wrapping box, and a Recheck button.
/// The texts follow the view model, so Recheck and edits of the field redraw them. The page is never blocked: it is how an unusable Data
/// Directory is repaired.
/// </summary>
public static class DataDirectoryPage
{
    public const string Title = "Data Directory";

    private const string NetworkShareWarning = "This looks like a network share. SQLite locking over a network share is unreliable; use a local disk if you can.";

    public static void Register(PageCatalog catalog) =>
        catalog.Register(new PageDefinition(Title, vm => PageCatalog.GroupBadge(vm, Title), ctx => Build(ctx.Vm)));

    private static View Build(SettingsPageViewModel vm)
    {
        var path = Line(vm, "Path", v => v.DataDirectoryPath);
        var status = Line(vm, "Status", v => v.DataDirectoryStatus);
        var free = Line(vm, "Free space", v => v.DataDirectoryFreeSpace);
        var database = Line(vm, "Upload State database", v => v.DataDirectoryDatabaseSize);
        var network = Wrapped(vm, Theme.Locked, v => v.DataDirectoryOnNetworkShare ? NetworkShareWarning : "");
        var split = Wrapped(vm, Theme.Locked, v => v.SplitStateWarning);
        var problem = Wrapped(vm, Theme.Error, v => v.DataDirectoryProblem);
        var fixHeading = Wrapped(vm, Theme.Help, v => v.HasDataDirectoryProblem ? "No Run can start until an administrator runs:" : "");
        var fix = Wrapped(vm, null, v => v.DataDirectoryFixCommand);
        var staging = Wrapped(vm, Theme.Locked, v => v.StagingWarning);

        var rows = new List<View>
        {
            FormRows.Note("Holds the Upload State, Staging Areas, logs and Reports shared by every account on this machine."),
            FormRows.Field(vm.Field("State:Path")),
            path, status, free, database,
            network, split, problem, fixHeading, fix,
            Recheck(vm),
            staging,
        };
        return new FormPane(rows);
    }

    private static View Recheck(SettingsPageViewModel vm)
    {
        var row = new View { Width = Dim.Fill(), Height = 1, CanFocus = true, TabStop = TabBehavior.NoStop };
        row.Add(FormRows.Btn("Recheck", () => vm.RecheckDataDirectoryCommand.Fire(row)));
        return row;
    }

    private static View Line(SettingsPageViewModel vm, string label, Func<SettingsPageViewModel, string> text)
    {
        var row = new View { Width = Dim.Fill(), Height = 1 };
        var value = new Label { X = FormRows.LabelWidth + 1, Width = Dim.Fill(1), Text = text(vm) };
        row.Add(new Label { Text = FormRows.Fit(label, FormRows.LabelWidth) }.Apply(Theme.Help), value);
        Follow(row, vm, () => value.Text = text(vm));
        return row;
    }

    /// <summary>
    /// A block of wrapped text with as many lines as it needs, none when there is nothing to say (the full fix command must never be cut off);
    /// <paramref name="scheme"/> null keeps the pane colours.
    /// </summary>
    private static View Wrapped(SettingsPageViewModel vm, Terminal.Gui.Drawing.Scheme? scheme, Func<SettingsPageViewModel, string> text)
    {
        var label = new Label { X = 0, Width = Dim.Fill(1), Height = Dim.Auto(DimAutoStyle.Text), Text = text(vm) };
        label.TextFormatter.WordWrap = true;
        if (scheme is not null) label.SetScheme(scheme);
        Follow(label, vm, () => label.Text = text(vm));
        return label;
    }

    private static void Follow(View view, SettingsPageViewModel vm, Action update)
    {
        PropertyChangedEventHandler handler = (_, _) => update();
        vm.PropertyChanged += handler;
        view.Disposing += (_, _) => vm.PropertyChanged -= handler;
    }
}

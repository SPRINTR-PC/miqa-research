using System;
using System.Linq;
using Avalonia.Controls;
using Avalonia.Input;
using MiresSftpUploader.Prototype;

namespace MiresSftpUploader.Views;

// PROTOTYPE: variant switcher host (throwaway).
public partial class MainWindow : Window
{
    static readonly (string Key, string Name, Func<Control> Make)[] Variants =
    [
        ("B", "Upload page (chosen layout)", () => new VariantB()),
        ("H1", "History: master-detail", () => new HistoryH1()),
        ("H2", "History: table, then drill-in", () => new HistoryH2()),
        ("H3", "History: timeline feed", () => new HistoryH3()),
    ];
    int _index, _lastHistory = 1;
    bool _syncing;

    public MainWindow()
    {
        InitializeComponent();
        var wanted = Environment.GetCommandLineArgs().Select(a => a.StartsWith("--variant=") ? a[10..] : null).FirstOrDefault(a => a != null)
                     ?? Environment.GetEnvironmentVariable("MIRES_PROTO_VARIANT");
        _index = Math.Max(0, Array.FindIndex(Variants, v => string.Equals(v.Key, wanted, StringComparison.OrdinalIgnoreCase)));
        this.FindControl<Button>("Prev")!.Click += (_, _) => Show(_index - 1);
        this.FindControl<Button>("Next")!.Click += (_, _) => Show(_index + 1);
        KeyDown += (_, e) =>
        {
            if (e.Source is TextBox) return;
            if (e.Key == Key.Left) Show(_index - 1);
            else if (e.Key == Key.Right) Show(_index + 1);
        };
        Show(_index);
        DataContextChanged += (_, _) =>
        {
            if (DataContext is not ProtoVm pv) return;
            pv.PropertyChanged += (_, e) =>
            {
                if (e.PropertyName != nameof(ProtoVm.Page) || _syncing) return;
                if (pv.Page == 0) Show(0); else if (_index == 0) Show(_lastHistory);
            };
            Show(_index);
        };
        // screenshot helpers (prototype only)
        Opened += (_, _) =>
        {
            if (Environment.GetEnvironmentVariable("MIRES_PROTO_THEME") == "Light" && DataContext is ProtoVm t) t.ThemeCmd.Execute().Subscribe();
            if (Environment.GetEnvironmentVariable("MIRES_PROTO_AUTOSTART") is { } n && DataContext is ProtoVm vm)
            {
                vm.StartCmd.Execute().Subscribe();
                var timer = new Avalonia.Threading.DispatcherTimer { Interval = TimeSpan.FromSeconds(int.Parse(n)) };
                timer.Tick += (_, _) => { timer.Stop(); if (Environment.GetEnvironmentVariable("MIRES_PROTO_SETTINGS") == "1") vm.SettingsCmd.Execute().Subscribe(); };
                timer.Start();
            }
        };
    }

    void Show(int i)
    {
        _index = (i + Variants.Length) % Variants.Length;
        var v = Variants[_index];
        if (_index > 0) _lastHistory = _index;
        if (DataContext is ProtoVm vm)
        {
            _syncing = true; vm.Page = _index == 0 ? 0 : 1; _syncing = false;
            if (_index == 1) vm.SelectedRun ??= vm.VisibleRuns.FirstOrDefault(); else if (_index > 1) vm.SelectedRun = null;
        }
        this.FindControl<ContentControl>("Host")!.Content = v.Make();
        this.FindControl<TextBlock>("VariantLabel")!.Text = $"{v.Key} ({v.Name})";
    }
}

using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Linq;
using System.Text.RegularExpressions;
using MiresSftpUploader.SettingsTui;
using MiresSftpUploader.ViewModels;
using Terminal.Gui.Drawing;
using Terminal.Gui.Input;
using Terminal.Gui.ViewBase;
using Terminal.Gui.Views;

namespace MiresSftpUploader.Tui;

/// <summary>
/// The Help page of the whole-app TUI: the topics of <see cref="HelpViewModel"/> (the same Markdown as the window) plus the TUI-only Keys topic.
/// Left: the topic list (20 columns); right: Terminal.Gui's built-in Markdown view, scrollable. Tab switches between the two panes.
/// </summary>
public sealed partial class HelpPage : View, IShellPage
{
    public const int TopicListWidth = 20;
    public const string KeysTitle = "Keys";

    private readonly HelpViewModel _vm;
    private readonly ListView _topics;
    private readonly FrameView _right = new() { X = TopicListWidth, Y = 0, Width = Dim.Fill(), Height = Dim.Fill(), BorderStyle = LineStyle.Single };
    private readonly Terminal.Gui.Views.Markdown _viewer;
    private string _status = "";
    private bool _syncing;

    public HelpPage(HelpViewModel vm)
    {
        _vm = vm;
        CanFocus = true;
        var left = new FrameView { X = 0, Y = 0, Width = TopicListWidth, Height = Dim.Fill(), Title = "Topics", BorderStyle = LineStyle.Single };
        _topics = new ListView
        {
            Width = Dim.Fill(), Height = Dim.Fill(),
            Source = new ListWrapper<string>(new ObservableCollection<string>(vm.Topics.Select(t => t.Title))),
        };
        _topics.SetScheme(Theme.Nav);
        left.SetScheme(Theme.Pane);
        left.Add(_topics);
        _viewer = new Terminal.Gui.Views.Markdown { Width = Dim.Fill(), Height = Dim.Fill(), ShowHeadingPrefix = true, CanFocus = true };
        _viewer.SetScheme(Theme.Pane);
        _right.SetScheme(Theme.Pane);
        _right.Add(_viewer);
        Add(left, _right);
        // Without a selected item the first Down only selects the first topic.
        _topics.SelectedItem = Math.Max(vm.Topics.ToList().IndexOf(vm.Selected), 0);

        _topics.ValueChanged += (_, e) =>
        {
            if (_syncing || e.NewValue is not { } i || i < 0 || i >= vm.Topics.Count) return;
            vm.Selected = vm.Topics[i];
            Show();
        };
        // Tab switches panes; the list and the text otherwise keep Tab for themselves (or hand it to the shell).
        _topics.KeyDown += (_, k) => SwitchPane(k, _viewer);
        _viewer.KeyDown += (_, k) => { if (!SwitchPane(k, _topics)) Scroll(k); };
        _viewer.LinkClicked += (_, e) =>
        {
            e.Handled = true;
            Follow(e.Url);
        };
        Show();
    }

    private static bool SwitchPane(Key key, View target)
    {
        if (key != Key.Tab && key != Key.Tab.WithShift) return false;
        target.SetFocus();
        key.Handled = true;
        return true;
    }

    private void Scroll(Key key)
    {
        var page = Math.Max(_viewer.Viewport.Height - 1, 1);
        var last = Math.Max(_viewer.GetContentSize().Height - _viewer.Viewport.Height, 0);
        int? y = null;
        if (key == Key.CursorUp) y = _viewer.Viewport.Y - 1;
        else if (key == Key.CursorDown) y = _viewer.Viewport.Y + 1;
        else if (key == Key.PageUp) y = _viewer.Viewport.Y - page;
        else if (key == Key.PageDown) y = _viewer.Viewport.Y + page;
        else if (key == Key.Home) y = 0;
        else if (key == Key.End) y = last;
        if (y is null) return;
        _viewer.Viewport = _viewer.Viewport with { Y = Math.Clamp(y.Value, 0, last) };
        key.Handled = true;
    }

    /// <summary>The topics of the TUI: the window's topics and the Keys topic (TUI only).</summary>
    public static HelpViewModel CreateViewModel(Action<Uri> openInBrowser)
    {
        var shared = HelpViewModel.Create(openInBrowser).Topics
            .Select(t => t.FileName is null && t.Title == "Command line" ? t with { Markdown = CommandLineMarkdown() } : t);
        return new HelpViewModel([.. shared, new HelpTopic(KeysTitle, KeysTopic.Markdown)], openInBrowser);
    }

    public HelpViewModel ViewModel => _vm;

    public Terminal.Gui.Views.Markdown Viewer => _viewer;

    public ListView Topics => _topics;

    /// <summary>The Markdown the viewer shows (after the TUI preprocessing of external links).</summary>
    public string ShownMarkdown => _viewer.Text;

    public string StatusText => _status.Length > 0 ? _status : $"Help: {_vm.Selected.Title}";

    public string KeyHints => "Up/Down Topic or scroll   Tab Switch pane";

    public event Action? ChromeChanged;

    public bool HandleKey(Key key) => false;

    public void FocusDefault()
    {
        if (!IsInitialized) return;
        // Keep the pane the user was in; the topic list the first time.
        if (_viewer.HasFocus || _topics.HasFocus) return;
        _topics.SetFocus();
    }

    /// <summary>Activates a link as the viewer does: a shipped document switches topic; an external address is shown in the status line.</summary>
    public void Follow(string url)
    {
        if (Uri.TryCreate(url, UriKind.Absolute, out var uri) && uri.Scheme is "http" or "https")
        {
            // A terminal cannot open a browser; the address is shown so the operator can copy it.
            _status = url;
            ChromeChanged?.Invoke();
            return;
        }

        var before = _vm.Selected;
        _vm.OpenLink(url);
        if (ReferenceEquals(before, _vm.Selected)) return;
        _syncing = true;
        _topics.SelectedItem = _vm.Topics.ToList().IndexOf(_vm.Selected);
        _syncing = false;
        Show();
    }

    private void Show()
    {
        _status = "";
        _viewer.Text = ForTerminal(_vm.Markdown);
        _right.Title = _vm.Selected.Title;
        SetNeedsDraw();
        ChromeChanged?.Invoke();
    }

    /// <summary>
    /// The Command line topic for the terminal. The built-in Markdown view does not scroll a code block sideways, so the <c>--help</c> text is not
    /// shown as one: each option becomes a list item that wraps at the pane width (the window keeps the code block).
    /// </summary>
    public static string CommandLineMarkdown() => CommandLineMarkdown(Core.Cli.HelpText);

    public static string CommandLineMarkdown(string helpText)
    {
        var output = new List<string> { "# Command line", "", "The same text as `MiresSftpUploader --help`." };
        var item = -1; // index in output of the list item being built
        var paragraph = -1;
        foreach (var raw in helpText.TrimEnd().Split('\n'))
        {
            var line = raw.TrimEnd();
            if (line.Length == 0)
            {
                item = paragraph = -1;
                continue;
            }

            var indent = line.Length - line.TrimStart().Length;
            var text = line.Trim();
            if (indent >= 4 && item >= 0)
            {
                output[item] += " " + text;
            }
            else if (indent >= 1)
            {
                var gap = Gap().Match(text);
                var entry = gap.Success ? $"`{text[..gap.Index]}` {Escape(text[(gap.Index + gap.Length)..])}" : Escape(text);
                if (output[^1].Length > 0 && item < 0) output.Add("");
                output.Add("- " + entry);
                item = output.Count - 1;
                paragraph = -1;
            }
            else if (paragraph >= 0 && !output[paragraph].EndsWith(':'))
            {
                output[paragraph] += " " + text;
            }
            else
            {
                output.Add("");
                output.Add(text);
                paragraph = output.Count - 1;
                item = -1;
            }
        }

        return string.Join("\n", output) + "\n";
    }

    private static string Escape(string text) => text.Replace("<", "\\<", StringComparison.Ordinal);

    [GeneratedRegex(@"\s{2,}")]
    private static partial Regex Gap();

    /// <summary>
    /// A terminal shows no link target, so an external link <c>[text](https://x)</c> becomes <c>[text (https://x)](https://x)</c>: the address is
    /// readable on screen and still a link whose activation puts it in the status line.
    /// </summary>
    public static string ForTerminal(string markdown) => ExternalLink().Replace(markdown, m =>
    {
        var text = m.Groups["text"].Value;
        var url = m.Groups["url"].Value;
        return text.Contains(url, StringComparison.Ordinal) ? m.Value : $"[{text} ({url})]({url})";
    });

    [GeneratedRegex(@"\[(?<text>[^\]]+)\]\((?<url>https?://[^)\s]+)\)")]
    private static partial Regex ExternalLink();
}

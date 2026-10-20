using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Reactive;
using MiresSftpUploader.Core;
using ReactiveUI;

namespace MiresSftpUploader.ViewModels;

/// <summary>One page of the Help: a title and the Markdown shown for it.</summary>
public sealed record HelpTopic(string Title, string Markdown, string? FileName = null);

/// <summary>
/// The Help page: the README, the scheduling guide and the command-line reference, each as Markdown. The README and
/// the guide are embedded in the executable; the command-line reference is the same text as <c>--help</c>.
/// </summary>
public sealed class HelpViewModel : ViewModelBase
{
    private readonly Action<Uri> _openInBrowser;
    private HelpTopic _selected;

    public HelpViewModel(IReadOnlyList<HelpTopic> topics, Action<Uri> openInBrowser)
    {
        Topics = topics;
        _selected = topics[0];
        _openInBrowser = openInBrowser;
        OpenLinkCommand = ReactiveCommand.Create<string>(OpenLink);
    }

    public IReadOnlyList<HelpTopic> Topics { get; }

    public HelpTopic Selected
    {
        get => _selected;
        set
        {
            this.RaiseAndSetIfChanged(ref _selected, value);
            this.RaisePropertyChanged(nameof(Markdown));
        }
    }

    public string Markdown => Selected.Markdown;

    /// <summary>Bound to the Markdown viewer's link command; the parameter is the link target.</summary>
    public ReactiveCommand<string, Unit> OpenLinkCommand { get; }

    /// <summary>
    /// An http(s) link opens in the browser; a link to another shipped document (<c>scheduling.md</c>) switches topic.
    /// Anything else (file:, javascript:, a path) is ignored.
    /// </summary>
    public void OpenLink(string? href)
    {
        if (string.IsNullOrWhiteSpace(href)) return;
        if (Uri.TryCreate(href, UriKind.Absolute, out var uri))
        {
            if (uri.Scheme is "http" or "https") _openInBrowser(uri);
            return;
        }

        var file = Path.GetFileName(href.Split('#')[0]);
        if (Topics.FirstOrDefault(t => string.Equals(t.FileName, file, StringComparison.OrdinalIgnoreCase)) is { } topic)
            Selected = topic;
    }

    public static HelpViewModel Create(Action<Uri> openInBrowser) => new(
    [
        new HelpTopic("Overview", Embedded("README.md"), "README.md"),
        new HelpTopic("Scheduling", Embedded("scheduling.md"), "scheduling.md"),
        new HelpTopic("Command line", "# Command line\n\nThe same text as `MiresSftpUploader --help`.\n\n```\n" + Cli.HelpText.TrimEnd() + "\n```\n"),
    ], openInBrowser);

    private static string Embedded(string name)
    {
        var assembly = typeof(HelpViewModel).Assembly;
        using var stream = assembly.GetManifestResourceStream("help/" + name);
        if (stream is null) return $"# Not available\n\n`{name}` is not embedded in this build.";
        using var reader = new StreamReader(stream);
        return reader.ReadToEnd();
    }
}

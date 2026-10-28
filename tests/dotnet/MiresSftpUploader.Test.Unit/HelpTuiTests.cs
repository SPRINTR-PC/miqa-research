using MiresSftpUploader.Core;
using MiresSftpUploader.Test.Support;
using MiresSftpUploader.Tui;
using MiresSftpUploader.ViewModels;
using Terminal.Gui.Input;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class HelpTuiTests : ConfigurationTestBase
{
    private readonly List<TuiTestHost> _hosts = [];

    [TestCleanup]
    public void CloseHosts()
    {
        foreach (var h in _hosts) h.Dispose();
    }

    private sealed record Started(TuiTestHost Host, TuiShell Shell, HelpPage Help, List<Uri> Opened);

    private Started Start(int width = 100, int height = 32, IReadOnlyList<HelpTopic>? topics = null)
    {
        var opened = new List<Uri>();
        var vm = topics is null ? HelpPage.CreateViewModel(opened.Add) : new HelpViewModel(topics, opened.Add);
        var settings = new SettingsPageViewModel(Create(ValidMachine().ToJsonString()));
        HelpPage? help = null;
        TuiShell? shell = null;
        var host = new TuiTestHost(app =>
        {
            help = new HelpPage(vm);
            return shell = new TuiShell(app, settings, new FakeTuiDialogs(), ShellTab.Help, help: help);
        }, width, height);
        _hosts.Add(host);
        host.WaitUntil(() => shell!.IsInitialized && shell.Current == ShellTab.Help, "shell on Help");
        return new Started(host, shell!, help!, opened);
    }

    private static readonly IReadOnlyList<HelpTopic> Linked =
    [
        new("Overview", "# Overview\n\nSee [the guide](scheduling.md) or [the site](https://example.org/x).\n", "README.md"),
        new("Scheduling", "# Scheduling\n\nHow to schedule.\n", "scheduling.md"),
    ];

    private static string LongTopic() =>
        "# Long\n\n" + string.Join("\n\n", Enumerable.Range(1, 60).Select(i => "paragraph " + i));

    private static int Scrolled(Started s) => s.Host.OnUi(() => s.Help.Viewer.Viewport.Y);

    [TestMethod, Timeout(60000)]
    public void Help_lists_the_topics_and_shows_the_first()
    {
        var s = Start();
        s.Host.WaitUntilShows("# MIRES SFTP Uploader");
        foreach (var title in new[] { "Overview", "Scheduling", "Command line", "Keys" }) Assert.IsTrue(s.Host.Shows(title), title);
        Assert.IsTrue(s.Host.Lines.Any(l => l.Contains("Topics")), "topic list frame");
    }

    [TestMethod, Timeout(60000)]
    public void Down_in_the_topic_list_switches_the_topic()
    {
        var s = Start();
        s.Host.Press(Key.CursorDown);
        s.Host.WaitUntilShows("# Scheduling Headless Runs");
        Assert.AreEqual("Scheduling", s.Host.OnUi(() => s.Help.ViewModel.Selected.Title));
        Assert.IsTrue(s.Host.Shows("Help: Scheduling"), "status line follows the topic");
    }

    [TestMethod, Timeout(60000)]
    public void The_topic_list_is_twenty_columns_wide()
    {
        var s = Start();
        Assert.AreEqual(20, s.Host.OnUi(() => s.Help.Topics.SuperView!.Frame.Width));
    }

    [TestMethod, Timeout(60000)]
    public void Tab_switches_between_the_topic_list_and_the_text()
    {
        var s = Start();
        StringAssert.StartsWith(s.Host.FocusPath, "ListView");
        s.Host.Press(Key.Tab);
        StringAssert.StartsWith(s.Host.FocusPath, "Markdown");
        s.Host.Press(Key.Tab);
        StringAssert.StartsWith(s.Host.FocusPath, "ListView");
    }

    [TestMethod, Timeout(60000)]
    public void Keys_scroll_the_text_when_it_has_the_focus()
    {
        var s = Start(80, 24, [new("Long", LongTopic(), "long.md")]);
        s.Host.Press(Key.Tab);
        Assert.AreEqual(0, Scrolled(s));
        s.Host.Press(Key.CursorDown);
        Assert.AreEqual(1, Scrolled(s));
        s.Host.Press(Key.CursorUp);
        Assert.AreEqual(0, Scrolled(s));
        s.Host.Press(Key.PageDown);
        Assert.IsTrue(Scrolled(s) > 10, "a page down moves by about a screen");
        s.Host.Press(Key.PageUp);
        Assert.AreEqual(0, Scrolled(s));
        s.Host.Press(Key.End);
        s.Host.WaitUntilShows("paragraph 60");
        s.Host.Press(Key.Home);
        s.Host.WaitUntilShows("# Long");
        Assert.AreEqual(0, Scrolled(s));
    }

    [TestMethod, Timeout(60000)]
    public void Focus_works_after_leaving_Help_and_coming_back()
    {
        var s = Start();
        s.Host.Press(Key.F9);
        s.Host.Press(Key.F12);
        s.Host.Press(Key.CursorDown);
        s.Host.WaitUntilShows("# Scheduling Headless Runs");
        s.Host.Press(Key.Tab);
        s.Host.Press(Key.F10);
        s.Host.Press(Key.F12);
        StringAssert.StartsWith(s.Host.FocusPath, "Markdown", "the pane the user left is kept");
    }

    [TestMethod, Timeout(60000)]
    public void A_link_to_another_document_switches_the_topic()
    {
        var s = Start(100, 32, Linked);
        var lines = s.Host.Lines;
        var y = Array.FindIndex(lines, l => l.Contains("the guide"));
        s.Host.Click(lines[y].IndexOf("the guide", StringComparison.Ordinal) + 2, y);
        s.Host.WaitUntilShows("How to schedule.");
        Assert.AreEqual(1, s.Host.OnUi(() => s.Help.Topics.SelectedItem), "the topic list follows");
        Assert.AreEqual("Scheduling", s.Host.OnUi(() => s.Help.ViewModel.Selected.Title));
        Assert.AreEqual(0, s.Opened.Count, "a shipped document opens nothing outside");
    }

    [TestMethod, Timeout(60000)]
    public void An_external_link_shows_its_address_in_the_text_and_the_status_line_when_activated()
    {
        var s = Start(100, 32, Linked);
        s.Host.WaitUntilShows("the site (https://example.org/x)");
        var lines = s.Host.Lines;
        var y = Array.FindIndex(lines, l => l.Contains("the site"));
        s.Host.Click(lines[y].IndexOf("the site", StringComparison.Ordinal) + 2, y);
        s.Host.WaitUntil(() => s.Shell.StatusText == "https://example.org/x", "status line shows the address");
        Assert.AreEqual(0, s.Opened.Count, "the terminal opens no browser");
        Assert.AreEqual("Overview", s.Host.OnUi(() => s.Help.ViewModel.Selected.Title));
    }

    [TestMethod]
    public void External_links_are_rewritten_for_the_terminal_only()
    {
        const string source = "a [text](https://x.org/p?q=1) b [https://y.org](https://y.org) c [doc](scheduling.md)";
        var shown = HelpPage.ForTerminal(source);
        Assert.AreEqual("a [text (https://x.org/p?q=1)](https://x.org/p?q=1) b [https://y.org](https://y.org) c [doc](scheduling.md)", shown);
        Assert.IsTrue(HelpViewModel.Create(_ => { }).Topics.All(t => !t.Markdown.Contains("(https://") || t.Markdown.Contains("](")), "window text untouched");
    }

    [TestMethod, Timeout(60000)]
    public void The_Keys_topic_exists_and_lists_the_global_keys_and_every_page()
    {
        var s = Start();
        Assert.IsTrue(s.Help.ViewModel.Topics.Any(t => t.Title == "Keys"));
        Assert.IsFalse(HelpViewModel.Create(_ => { }).Topics.Any(t => t.Title == "Keys"), "TUI only: the window's Help has no Keys topic");
        s.Host.Press(Key.CursorDown);
        s.Host.Press(Key.CursorDown);
        s.Host.Press(Key.CursorDown);
        s.Host.WaitUntilShows("# Keys");
        var keys = s.Help.ViewModel.Selected.Markdown;
        foreach (var expected in new[] { "F9", "F10", "F11", "F12", "Ctrl+Q", "## Upload", "## History", "## Settings", "## Help" })
            StringAssert.Contains(keys, expected);
    }

    [TestMethod, Timeout(60000)]
    public void Command_line_topic_is_readable_at_80_columns()
    {
        var s = Start(80, 24);
        s.Host.Press(Key.CursorDown);
        s.Host.Press(Key.CursorDown);
        s.Host.WaitUntilShows("# Command line");
        s.Host.Press(Key.Tab);
        var seen = new HashSet<string>();
        for (var i = 0; i < 12; i++)
        {
            foreach (var l in s.Host.Lines) seen.Add(l);
            s.Host.Press(Key.PageDown);
        }

        var all = string.Join("\n", seen);
        // The end of long option descriptions is on screen, not clipped at the pane edge.
        StringAssert.Contains(all, "exit; runs nothing.");
        StringAssert.Contains(all, "(including host key mismatch)");
        StringAssert.Contains(all, "Another Run holds the lock");
    }

    [TestMethod, Timeout(60000)]
    public void Scheduling_table_is_readable_at_80_columns()
    {
        var s = Start(80, 24);
        s.Host.Press(Key.CursorDown);
        s.Host.WaitUntilShows("# Scheduling Headless Runs");
        s.Host.Press(Key.Tab);
        var tables = new List<string>();
        for (var i = 0; i < 30; i++)
        {
            var lines = s.Host.Lines;
            if (lines.Any(l => l.Contains("What to check"))) tables.AddRange(lines);
            s.Host.Press(Key.PageDown);
        }

        // The widest table (three columns) keeps all its borders and headers inside the 80-column pane; cells wrap instead of clipping.
        var header = tables.FirstOrDefault(l => l.Contains("Exit code") && l.Contains("Meaning") && l.Contains("What to check"));
        Assert.IsNotNull(header, "the exit code table header is fully on screen");
        Assert.IsTrue(tables.Any(l => l.Contains("┌") && l.Contains("┐")), "the table's right edge is on screen");
        Assert.IsTrue(tables.Any(l => l.Contains("Nothing.")), "the cells wrap and show their text");
    }

    [TestMethod]
    public void The_terminal_Command_line_topic_wraps_options_instead_of_a_code_block()
    {
        var md = HelpPage.CommandLineMarkdown("Usage: X [options]\n\nOptions:\n  --a <n>   Long text\n            continues here.\n  --b       Short.\n\nExit codes:\n  0    OK\n");
        Assert.AreEqual("# Command line\n\nThe same text as `MiresSftpUploader --help`.\n\nUsage: X [options]\n\nOptions:\n\n- `--a <n>` Long text continues here.\n- `--b` Short.\n\nExit codes:\n\n- `0` OK\n", md);
        Assert.IsFalse(HelpPage.CommandLineMarkdown().Contains("```"));
        Assert.IsTrue(HelpViewModel.Create(_ => { }).Topics.Single(t => t.Title == "Command line").Markdown.Contains("```"), "the window keeps its code block");
    }
}

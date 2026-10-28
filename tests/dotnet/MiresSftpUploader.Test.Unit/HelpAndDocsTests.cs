using System.Text.RegularExpressions;
using MiresSftpUploader.Core;
using MiresSftpUploader.ViewModels;

namespace MiresSftpUploader.Test.Unit;

/// <summary>The shipped documentation, the scheduler samples and the Help page stay true to the command line.</summary>
[TestClass]
public sealed class HelpAndDocsTests
{
    private static string Shipped(string relative) => File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "shipped", relative));

    private static string[] SampleFiles => Directory.GetFiles(Path.Combine(AppContext.BaseDirectory, "shipped", "scheduler"));

    // ---- --help ----

    [TestMethod]
    public void Help_gives_a_default_for_every_flag_that_takes_a_value_and_names_the_precedence()
    {
        var help = Cli.HelpText;

        foreach (var line in help.Split('\n').Where(l => Regex.IsMatch(l, @"^\s+--(source|report|report-format|export-run|limit|log-level|data-dir) ")))
            Assert.IsTrue(Regex.IsMatch(line, "default|none", RegexOptions.IgnoreCase), $"No default stated: {line.Trim()}");
        foreach (var expected in new[] { "command-line flags", "MIRES_* environment variables", "appsettings.user.json", "appsettings.json" })
            StringAssert.Contains(help, expected);
        Assert.IsTrue(help.IndexOf("command-line flags", StringComparison.Ordinal) < help.IndexOf("appsettings.json next", StringComparison.Ordinal));
    }

    [TestMethod]
    public void Help_describes_configure_its_honoured_flags_and_its_terminal_requirement()
    {
        var line = Cli.HelpText.Split('\n').Single(l => l.TrimStart().StartsWith("--configure ", StringComparison.Ordinal));

        StringAssert.Contains(Cli.HelpText, "Settings TUI");
        StringAssert.Contains(Cli.HelpText, "--data-dir and --log-level");
        StringAssert.Contains(Cli.HelpText, "80x24");
        Assert.IsTrue(line.Length > 0);
        StringAssert.Contains(Cli.HelpText, "--configure and --version imply --headless", StringComparison.Ordinal);
    }

    [TestMethod]
    public void Help_names_the_supported_platforms_of_the_Settings_TUI_and_that_Windows_is_unverified()
    {
        StringAssert.Contains(Cli.HelpText, "Linux and macOS");
        StringAssert.Contains(Cli.HelpText, "Windows is unverified");
    }

    [TestMethod]
    public void The_readme_the_scheduling_guide_and_the_Help_page_document_the_Settings_TUI()
    {
        var help = HelpViewModel.Create(_ => { });
        foreach (var text in new[] { Shipped("README.md"), Shipped("scheduling.md"), help.Topics[0].Markdown, help.Topics[1].Markdown })
        {
            StringAssert.Contains(text, "--configure");
            StringAssert.Contains(text, "Settings TUI");
            StringAssert.Contains(text, "Linux and macOS");
            StringAssert.Contains(text, "Windows is unverified");
        }
        var readme = Shipped("README.md");
        foreach (var key in new[] { "F5", "Ctrl+S", "Ctrl+R", "Ctrl+Q", "F4", "Ctrl+PageUp", "Tab completion", "Check connection" })
            StringAssert.Contains(readme, key);
    }

    [TestMethod]
    public void The_release_checklist_has_the_manual_Settings_TUI_items_and_dialogs_are_driven_headlessly()
    {
        var text = Shipped("release-checklist.md");

        foreach (var item in new[] { "Settings TUI", "SSH session", "throttled", "Resize while running", "TERM=dumb", "256-colour", "PuTTY",
                     "Unlock", "unsaved changes", "Archive Rules", "SIGHUP", "130", "linux-arm64", "osx-arm64", "headless", "Windows console" })
            StringAssert.Contains(text, item, StringComparison.OrdinalIgnoreCase);
    }

    [TestMethod]
    public void The_publish_scripts_smoke_test_configure_under_redirected_streams()
    {
        var root = Path.Combine(AppContext.BaseDirectory, "shipped");
        foreach (var script in new[] { "publish.sh", "publish.ps1" })
        {
            var text = File.ReadAllText(Path.Combine(root, script));
            StringAssert.Contains(text, "--configure", script);
        }
    }

    [TestMethod]
    public void Help_describes_tui_its_honoured_flags_exit_2_and_configure_as_the_Settings_shortcut()
    {
        var line = Cli.HelpText.Split('\n').Single(l => l.TrimStart().StartsWith("--tui ", StringComparison.Ordinal));
        var block = Cli.HelpText[Cli.HelpText.IndexOf(line, StringComparison.Ordinal)..];

        foreach (var expected in new[] { "F9-F12", "exit 2", "--configure is the", "shortcut", "Settings", "data directory and log level" })
            StringAssert.Contains(block, expected);
        StringAssert.Contains(Cli.HelpText, "and so does --tui");
    }

    [TestMethod]
    public void The_readme_documents_the_TUI_pages_and_the_keys_of_every_page_without_placeholder_text()
    {
        var readme = Shipped("README.md");
        var section = readme[readme.IndexOf("## TUI", StringComparison.Ordinal)..readme.IndexOf("## Settings TUI", StringComparison.Ordinal)];

        foreach (var key in new[] { "F9", "F12", "Ctrl+Q", "Upload", "History", "Help", "Space", "End follows", "F5 refreshes", "J or C", "Log pane" })
            StringAssert.Contains(section, key);
        Assert.IsFalse(section.Contains("placeholder", StringComparison.OrdinalIgnoreCase), "README still describes placeholder pages");
        Assert.IsFalse(section.Contains("This release ships", StringComparison.Ordinal));
    }

    [TestMethod]
    public void The_Keys_topic_lists_the_keys_of_the_Upload_and_History_pages()
    {
        var keys = MiresSftpUploader.Tui.KeysTopic.Markdown;

        foreach (var expected in new[] { "R Run", "D Dry run", "S Scan", "X Cancel", "T Retry", "1-4", "L shows", "End follows", "1-3", "F Failed", "J / C", "F5" })
            StringAssert.Contains(keys, expected);
    }

    [TestMethod]
    public void The_scheduling_guide_points_at_the_TUI_for_a_headless_machine_over_SSH()
    {
        var text = Shipped("scheduling.md");

        StringAssert.Contains(text, "--tui");
        StringAssert.Contains(text, "SSH");
    }

    [TestMethod]
    public void The_release_checklist_has_the_whole_app_TUI_section_with_its_manual_items()
    {
        var text = Shipped("release-checklist.md");
        var section = text[text.IndexOf("## 15. Whole-app TUI", StringComparison.Ordinal)..];

        foreach (var item in new[] { "gnome-terminal", "iTerm", "Guake", "WinExe", "100,000", "throttled", "Resize during a Run", "SIGHUP", "SIGTERM", "130", "cancelled",
                     "PuTTY", "Windows Terminal", "▶ ✓ ✗ ⊘ … ●", "16-colour", "256-colour", "two operators", "linux-x64", "linux-arm64", "osx-arm64" })
            StringAssert.Contains(section, item, StringComparison.OrdinalIgnoreCase);
        Assert.IsFalse(section.Contains("This ticket ships", StringComparison.Ordinal));
    }

    [TestMethod]
    public void The_publish_scripts_smoke_test_tui_under_redirected_streams()
    {
        foreach (var script in new[] { "publish.sh", "publish.ps1" })
            StringAssert.Contains(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "shipped", script)), "--tui", script);
    }

    [TestMethod]
    public void The_glossary_defines_TUI_and_the_Settings_TUI()
    {
        var glossary = Shipped("GLOSSARY.md");

        StringAssert.Contains(glossary, "**TUI**");
        StringAssert.Contains(glossary, "_Avoid_");
        StringAssert.Contains(glossary, "_Avoid_: Console UI, terminal mode");
    }

    [TestMethod]
    public void Help_lists_every_exit_code()
    {
        foreach (var code in new[] { "0", "1", "2", "3", "4", "130" })
            Assert.IsTrue(Regex.IsMatch(Cli.HelpText, $@"^\s+{code}\s{{2,}}\S", RegexOptions.Multiline), $"Exit code {code} is not in --help");
    }

    // ---- documents and samples only use flags and exit codes that exist ----

    [TestMethod]
    public void Documents_and_samples_use_only_flags_that_exist()
    {
        var known = Regex.Matches(Cli.HelpText, @"--[a-z][a-z-]*").Select(m => m.Value).ToHashSet();
        var texts = new[] { "README.md", "scheduling.md" }.Select(Shipped).Concat(SampleFiles.Select(File.ReadAllText));

        foreach (var flag in texts.SelectMany(t => Regex.Matches(t, @"(?<![\w-])--[a-z][a-z-]*").Select(m => m.Value)).Distinct()
                     .Where(f => !ExternalFlags.Contains(f)))
            Assert.IsTrue(known.Contains(flag), $"{flag} is documented but --help does not list it");
    }

    // Flags of other tools that the documents show (systemctl enable --now).
    private static readonly HashSet<string> ExternalFlags = ["--now"];

    [TestMethod]
    public void The_scheduling_guide_covers_every_scheduler_and_the_exit_code_table()
    {
        var text = Shipped("scheduling.md");

        foreach (var heading in new[] { "## Windows Task Scheduler", "## cron", "## systemd", "## launchd", "## First-setup checklist" })
            StringAssert.Contains(text, heading);
        foreach (var code in new[] { "| 0 |", "| 1 |", "| 2 |", "| 3 |", "| 4 |", "| 130 |" })
            StringAssert.Contains(text, code);
        foreach (var step in new[] { "--init-data-dir", "--validate-config --check-connection", "--dry-run" })
            StringAssert.Contains(text, step);
        Assert.IsTrue(text.IndexOf("--init-data-dir", StringComparison.Ordinal) < text.IndexOf("--validate-config --check-connection", StringComparison.Ordinal));
        Assert.IsTrue(text.IndexOf("--validate-config --check-connection", StringComparison.Ordinal) < text.IndexOf("--dry-run", StringComparison.Ordinal));
    }

    [TestMethod]
    public void The_readme_names_the_init_command_and_every_scheduler_sample()
    {
        var text = Shipped("README.md");

        StringAssert.Contains(text, "--init-data-dir");
        foreach (var sample in new[] { "task.xml", "crontab.example", "mires-sftp-uploader.timer", "eu.mires.sftp-uploader.plist" })
            StringAssert.Contains(text, sample);
    }

    [TestMethod]
    public void Every_scheduler_sample_is_shipped_and_none_contains_a_secret_value()
    {
        var names = SampleFiles.Select(Path.GetFileName).ToHashSet();
        foreach (var expected in new[] { "task.xml", "crontab.example", "mires-sftp-uploader.service", "mires-sftp-uploader.timer", "eu.mires.sftp-uploader.plist" })
            Assert.IsTrue(names.Contains(expected), $"{expected} is missing from scheduler/");

        foreach (var file in SampleFiles)
            Assert.IsFalse(Regex.IsMatch(File.ReadAllText(file), @"MIRES_(SFTP_PASSWORD|SFTP_KEY_PASSPHRASE|S3_\w+)\s*=\s*(?!Read-Secret|""\$\(|\.\.\.|\$)\S+"),
                $"{Path.GetFileName(file)} assigns a Secret");
    }

    [TestMethod]
    public void The_xml_and_plist_samples_are_well_formed()
    {
        foreach (var name in new[] { "task.xml", "eu.mires.sftp-uploader.plist" })
        {
            var doc = new System.Xml.XmlDocument { XmlResolver = null };
            doc.LoadXml(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "shipped", "scheduler", name)).Replace("<!DOCTYPE", "<!-- DOCTYPE").Replace("1.0.dtd\">", "1.0.dtd\" -->"));
        }
    }

    // ---- the Help page ----

    [TestMethod]
    public void The_help_view_model_offers_the_readme_the_scheduling_guide_and_the_command_line()
    {
        var help = HelpViewModel.Create(_ => { });

        CollectionAssert.AreEqual(new[] { "Overview", "Scheduling", "Command line" }, help.Topics.Select(t => t.Title).ToArray());
        Assert.AreEqual("Overview", help.Selected.Title);
        StringAssert.Contains(help.Topics[0].Markdown, "# MIRES SFTP Uploader");
        StringAssert.Contains(help.Topics[1].Markdown, "# Scheduling Headless Runs");
        StringAssert.Contains(help.Topics[2].Markdown, "--headless");
        StringAssert.Contains(help.Topics[2].Markdown, "Exit codes");
    }

    [TestMethod]
    public void Selecting_a_topic_changes_the_shown_markdown()
    {
        var help = HelpViewModel.Create(_ => { });

        help.Selected = help.Topics[1];

        Assert.AreEqual(help.Topics[1].Markdown, help.Markdown);
    }

    [TestMethod]
    public void External_links_open_in_the_browser_and_other_links_do_not()
    {
        var opened = new List<Uri>();
        var help = HelpViewModel.Create(opened.Add);

        help.OpenLink("https://example.org/page");
        help.OpenLink("http://example.org/");
        help.OpenLink("file:///etc/passwd");
        help.OpenLink("javascript:alert(1)");
        help.OpenLink("not a uri");

        CollectionAssert.AreEqual(new[] { "https://example.org/page", "http://example.org/" }, opened.Select(u => u.ToString()).ToArray());
    }

    [TestMethod]
    public void A_link_to_another_document_switches_topic_instead_of_opening_anything()
    {
        var opened = new List<Uri>();
        var help = HelpViewModel.Create(opened.Add);

        help.OpenLink("scheduling.md");

        Assert.AreEqual("Scheduling", help.Selected.Title);
        Assert.AreEqual(0, opened.Count);
    }
}

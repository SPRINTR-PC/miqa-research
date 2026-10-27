using System.Reactive.Linq;
using System.Reactive.Threading.Tasks;
using System.Linq;
using System.Text.Json.Nodes;
using MiresSftpUploader.Core;
using MiresSftpUploader.Test.Support;
using MiresSftpUploader.ViewModels;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class SettingsPageArchiveRulesTests : ConfigurationTestBase
{
    private static SettingsPageViewModel NewPage(Configuration cfg) =>
        new(cfg, path => new DataDirectoryAccess(path, true, true, "alice", "mires-uploader", 4096, 10L * 1024 * 1024 * 1024, false, "", null), _ => long.MaxValue);

    private static void Save(SettingsPageViewModel page) => page.SaveCommand.Execute().Subscribe();

    [TestMethod]
    public void Global_rules_are_shown_and_a_new_one_is_saved()
    {
        var machine = ValidMachine();
        machine["Archive"] = JsonNode.Parse("""{ "Rules": [ { "Name": "dicom", "Pattern": "\\.dcm$", "MinFiles": 5 } ] }""");
        var cfg = Create(machine.ToJsonString());
        var page = NewPage(cfg);

        Assert.HasCount(1, page.ArchiveRules.Rules);
        Assert.AreEqual("dicom", page.ArchiveRules.Rules[0].Name);
        Assert.AreEqual("5", page.ArchiveRules.Rules[0].MinFiles);
        Assert.AreEqual("PerDirectory", page.ArchiveRules.Rules[0].Grouping);
        Assert.IsFalse(page.ArchiveRules.IsChanged);

        page.ArchiveRules.AddRuleCommand.Execute().Subscribe();
        var added = page.ArchiveRules.Rules[1];
        added.Name = "logs";
        added.Pattern = @"\.log$";
        added.Grouping = "PerRule";
        added.ArchiveName = "{rule}-{date}.zip";
        Save(page);

        var saved = cfg.Load().Config!.Archive.Rules;
        CollectionAssert.AreEqual(new[] { "dicom", "logs" }, saved.Select(r => r.Name).ToArray());
        Assert.AreEqual(5, saved[0].MinFiles, "the existing rule is unchanged");
        Assert.AreEqual(ArchiveGrouping.PerRule, saved[1].Grouping);
        Assert.AreEqual("{rule}-{date}.zip", saved[1].ArchiveName);
        Assert.AreEqual(1, saved[1].MinFiles);
    }

    [TestMethod]
    public void Removing_the_last_global_rule_empties_the_list()
    {
        var machine = ValidMachine();
        machine["Archive"] = JsonNode.Parse("""{ "Rules": [ { "Name": "dicom", "Pattern": "\\.dcm$" } ] }""");
        var cfg = Create(machine.ToJsonString());
        var page = NewPage(cfg);

        page.ArchiveRules.RemoveRuleCommand.Execute(page.ArchiveRules.Rules[0]).Subscribe();
        Save(page);

        Assert.IsEmpty(cfg.Load().Config!.Archive.Rules);
    }

    [TestMethod]
    public void A_bad_pattern_and_a_duplicate_name_are_errors_on_the_rules_and_block_Save()
    {
        var page = NewPage(Create(ValidMachine().ToJsonString()));

        page.ArchiveRules.AddRuleCommand.Execute().Subscribe();
        page.ArchiveRules.AddRuleCommand.Execute().Subscribe();
        foreach (var rule in page.ArchiveRules.Rules) { rule.Name = "same"; rule.Pattern = "(unclosed"; }

        Assert.IsTrue(page.HasErrors);
        StringAssert.Contains(page.ArchiveRules.Error, "regular expression");
        StringAssert.Contains(page.ArchiveRules.Error, "not unique");
        Assert.IsFalse(page.SaveCommand.CanExecute.FirstAsync().ToTask().Result);

        page.ArchiveRules.Rules[1].Name = "other";
        foreach (var rule in page.ArchiveRules.Rules) rule.Pattern = @"\.dcm$";

        Assert.IsFalse(page.HasErrors);
    }

    [TestMethod]
    public void A_Sources_own_rules_are_edited_and_its_other_settings_are_kept()
    {
        var machine = ValidMachine();
        machine["Sources"]![0]!["Ignore"] = JsonNode.Parse("""{ "Files": ["skip.txt"] }""");
        machine["Sources"]![0]!["ArchiveRules"] = JsonNode.Parse("""[ { "Name": "slides", "Pattern": "\\.ndpi$", "Grouping": "PerRule" } ]""");
        var cfg = Create(machine.ToJsonString());
        var page = NewPage(cfg);
        var rules = page.Sources[0].ArchiveRules;

        Assert.AreEqual("slides", rules.Rules[0].Name);
        Assert.AreEqual("PerRule", rules.Rules[0].Grouping);
        Assert.IsFalse(page.Sources[0].IsChanged);

        rules.Rules[0].MinFiles = "3";
        Assert.IsTrue(page.Sources[0].IsChanged);
        rules.AddRuleCommand.Execute().Subscribe();
        rules.Rules[1].Name = "tiff";
        rules.Rules[1].Pattern = @"\.tiff?$";
        Save(page);

        var source = cfg.Load().Config!.Sources[0];
        CollectionAssert.AreEqual(new[] { "slides", "tiff" }, source.ArchiveRules.Select(r => r.Name).ToArray());
        Assert.AreEqual(3, source.ArchiveRules[0].MinFiles);
        CollectionAssert.AreEqual(new[] { "skip.txt" }, source.Ignore.Files.ToArray(), "Ignore Rules survive the save");
    }

    [TestMethod]
    public void Rules_from_the_environment_are_locked()
    {
        var cfg = Create(ValidMachine().ToJsonString(), env: new()
        {
            ["MIRES_Archive__Rules__0__Name"] = "envrule", ["MIRES_Archive__Rules__0__Pattern"] = @"\.dcm$",
        });

        var page = NewPage(cfg);

        Assert.IsTrue(page.ArchiveRules.IsLocked);
        Assert.AreEqual("envrule", page.ArchiveRules.Rules[0].Name);
        Assert.IsFalse(page.ArchiveRules.AddRuleCommand.CanExecute.FirstAsync().ToTask().Result);
    }

    [TestMethod]
    public async Task A_rule_saved_on_a_Source_in_the_page_archives_that_Sources_files_in_a_real_Run()
    {
        Directory.CreateDirectory(Path.Combine(DataDir, "p1"));
        File.WriteAllText(Path.Combine(DataDir, "p1", "a.dcm"), "alpha");
        File.WriteAllText(Path.Combine(DataDir, "p1", "b.dcm"), "beta");
        File.WriteAllText(Path.Combine(DataDir, "p1", "n.txt"), "notes");
        var machine = ValidMachine();
        machine["State"] = new JsonObject { ["Path"] = Path.Combine(Dir, "shared"), ["AccessGroup"] = TestAccessGroup.Name };
        var cfg = Create(machine.ToJsonString());
        var page = NewPage(cfg);
        page.Sources[0].ArchiveRules.AddRuleCommand.Execute().Subscribe();
        var rule = page.Sources[0].ArchiveRules.Rules[0];
        rule.Name = "dicom";
        rule.Pattern = @"\.dcm$";
        Save(page);

        var remote = new FakeRemote();
        var runtime = new UploaderRuntime(cfg, new StaticRemoteFactory(remote), Microsoft.Extensions.Logging.Abstractions.NullLoggerFactory.Instance,
            TimeProvider.System, CliOptions.Parse(["--headless"]).Options!);
        var result = await runtime.Prepare(headless: true).Engine!.RunAsync(new RunOptions(), new Progress<RunEvent>(), CancellationToken.None);

        Assert.AreEqual(0, result.ExitCode);
        Assert.IsTrue(remote.Files.Keys.Any(k => k.EndsWith("dicom-p1.zip")), string.Join(", ", remote.Files.Keys));
        Assert.IsFalse(remote.Files.Keys.Any(k => k.EndsWith("a.dcm")));
    }
}

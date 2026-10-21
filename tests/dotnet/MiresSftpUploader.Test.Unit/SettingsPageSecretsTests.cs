using System.Reactive.Linq;
using System.Reactive.Threading.Tasks;
using MiresSftpUploader.Core;
using MiresSftpUploader.ViewModels;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class SettingsPageSecretsTests : ConfigurationTestBase
{
    private const string Value = "hunter2-very-secret";

    private sealed record FixedIdentity(string? MachineId, string Account) : IMachineIdentity;

    private static readonly FixedIdentity Alice = new("machine-1", "alice");

    private string StorePath => Path.Combine(Dir, "user", "secrets.db");

    private Configuration CreateWithStore(Dictionary<string, string?>? env = null, IMachineIdentity? identity = null, bool withS3 = false)
    {
        var machine = ValidMachine();
        if (withS3)
            machine["Sources"]!.AsArray().Add(System.Text.Json.Nodes.JsonNode.Parse("""{ "Name": "wsi", "Type": "S3", "Endpoint": "https://s3.example.org", "Bucket": "b" }"""));
        File.WriteAllText(MachinePath, machine.ToJsonString());
        return new(new ConfigurationLocations(MachinePath, UserPath, env ?? [], StorePath, identity ?? Alice));
    }

    private static SettingsPageViewModel NewPage(Configuration cfg) =>
        new(cfg, path => new DataDirectoryAccess(path, true, true, "alice", "g", 4096, long.MaxValue, false, "", null), _ => long.MaxValue);

    private static bool Can(SecretEntryViewModel entry, System.Reactive.Unit _ = default) => entry.SaveCommand.CanExecute.FirstAsync().ToTask().Result;

    private static void Save(SecretEntryViewModel entry) => entry.SaveCommand.Execute().Subscribe();

    [TestMethod]
    public void Saving_a_typed_Secret_stores_it_clears_the_input_and_shows_it_as_stored()
    {
        var cfg = CreateWithStore();
        var page = NewPage(cfg);
        Assert.AreEqual("not set", page.SftpPassword.Status);

        page.SftpPassword.Input = Value;
        Save(page.SftpPassword);

        Assert.AreEqual("stored", page.SftpPassword.Status);
        Assert.AreEqual("", page.SftpPassword.Input);
        Assert.AreEqual(Value, cfg.LoadSecrets().SftpPassword);
        Assert.AreEqual("set", page.SftpPasswordStatus);
    }

    [TestMethod]
    public void A_Secret_from_the_environment_is_locked_and_cannot_be_saved_over()
    {
        var page = NewPage(CreateWithStore(new() { ["MIRES_SFTP_PASSWORD"] = "from-env" }));

        Assert.AreEqual("environment variable", page.SftpPassword.Status);
        Assert.IsTrue(page.SftpPassword.IsLocked);
        page.SftpPassword.Input = Value;
        Assert.IsFalse(Can(page.SftpPassword));
        Assert.IsFalse(page.SftpPasswordStatus == "not set");
    }

    [TestMethod]
    public void Save_needs_a_value()
    {
        var page = NewPage(CreateWithStore());

        Assert.IsFalse(Can(page.SftpPassword));
        page.SftpPassword.Input = Value;
        Assert.IsTrue(Can(page.SftpPassword));
    }

    [TestMethod]
    public void A_stored_Secret_can_be_cleared()
    {
        var cfg = CreateWithStore();
        var page = NewPage(cfg);
        page.SftpKeyPassphrase.Input = "phrase";
        Save(page.SftpKeyPassphrase);
        Assert.IsTrue(page.SftpKeyPassphrase.CanClear);

        page.SftpKeyPassphrase.ClearCommand.Execute().Subscribe();

        Assert.AreEqual("not set", page.SftpKeyPassphrase.Status);
        Assert.IsFalse(page.SftpKeyPassphrase.CanClear);
        Assert.IsNull(cfg.LoadSecrets().SftpKeyPassphrase);
    }

    [TestMethod]
    public void A_Secret_that_cannot_be_decrypted_says_to_re_enter_it_and_can_be_replaced()
    {
        using (var store = SecretStore.Open(StorePath, Alice)) store.Set("sftp-password", "old");
        var cfg = CreateWithStore(identity: new FixedIdentity("another-machine", "alice"));
        var page = NewPage(cfg);

        StringAssert.Contains(page.SftpPassword.Status, "re-enter");
        Assert.IsTrue(page.SftpPassword.CanClear);
        page.SftpPassword.Input = Value;
        Assert.IsTrue(Can(page.SftpPassword));
    }

    [TestMethod]
    public void Without_a_machine_identifier_the_Secret_boxes_are_disabled_with_the_reason()
    {
        var page = NewPage(CreateWithStore(identity: new FixedIdentity(null, "alice")));

        Assert.IsFalse(page.SftpPassword.StoreAvailable);
        StringAssert.Contains(page.SftpPassword.StoreProblem, "machine identifier");
        page.SftpPassword.Input = Value;
        Assert.IsFalse(Can(page.SftpPassword));
    }

    [TestMethod]
    public void A_stored_value_never_appears_in_anything_the_page_shows()
    {
        var cfg = CreateWithStore();
        var page = NewPage(cfg);
        page.SftpPassword.Input = Value;
        Save(page.SftpPassword);

        var shown = string.Join("|", page.Fields.Select(f => f.Value))
            + page.SftpPasswordStatus + page.SftpPassword.Status + page.SftpPassword.Input + page.SftpPassword.Error
            + string.Join("|", page.Sources.Select(s => s.SecretStatus)) + string.Join("|", page.Warnings) + string.Join("|", page.OtherErrors);

        Assert.DoesNotContain("hunter2", shown);
    }

    [TestMethod]
    public void Saving_a_Secret_keeps_unsaved_setting_edits()
    {
        var page = NewPage(CreateWithStore());
        page.Field("Sftp:Host").Value = "edited.example.org";

        page.SftpPassword.Input = Value;
        Save(page.SftpPassword);

        Assert.AreEqual("edited.example.org", page.Field("Sftp:Host").Value);
        Assert.IsTrue(page.HasChanges);
    }
}

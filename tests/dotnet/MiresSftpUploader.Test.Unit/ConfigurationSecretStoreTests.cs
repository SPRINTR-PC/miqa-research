using MiresSftpUploader.Core;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class ConfigurationSecretStoreTests : ConfigurationTestBase
{
    private sealed record FixedIdentity(string? MachineId, string Account) : IMachineIdentity;

    private static readonly FixedIdentity Alice = new("machine-1", "alice");

    private string StorePath => Path.Combine(Dir, "user", "secrets.db");

    private Configuration CreateWithStore(Dictionary<string, string?>? env = null, IMachineIdentity? identity = null) =>
        new(new ConfigurationLocations(MachinePath, UserPath, env ?? [], StorePath, identity ?? Alice));

    private void Store(string name, string value)
    {
        using var store = SecretStore.Open(StorePath, Alice);
        store.Set(name, value);
    }

    [TestMethod]
    public void A_stored_Secret_is_used_when_the_environment_does_not_supply_it()
    {
        File.WriteAllText(MachinePath, ValidMachine().ToJsonString());
        Store("sftp-password", "from-store");
        Store("sftp-key-passphrase", "phrase-from-store");
        Store("s3-access-key:Scans", "ak-store");
        Store("s3-secret-key:Scans", "sk-store");

        var secrets = CreateWithStore().LoadSecrets();

        Assert.AreEqual("from-store", secrets.SftpPassword);
        Assert.AreEqual("phrase-from-store", secrets.SftpKeyPassphrase);
        Assert.AreEqual("ak-store", secrets.S3("scans")!.AccessKey);
        Assert.AreEqual("sk-store", secrets.S3("SCANS")!.SecretKey);
    }

    [TestMethod]
    public void The_status_says_where_each_Secret_comes_from()
    {
        var machine = ValidMachine();
        machine["Sources"] = new System.Text.Json.Nodes.JsonArray(new System.Text.Json.Nodes.JsonObject
        {
            ["Name"] = "scans", ["Type"] = "S3", ["Endpoint"] = "https://s3.example.org", ["Bucket"] = "b",
        });
        File.WriteAllText(MachinePath, machine.ToJsonString());
        Store("sftp-password", "from-store");
        Store("sftp-key-passphrase", "phrase-from-store");
        Store("s3-secret-key:scans", "sk-store");

        var status = CreateWithStore(new() { ["MIRES_SFTP_PASSWORD"] = "from-env" }).Load().Secrets;

        Assert.AreEqual(SecretOrigin.Environment, status.OriginOf("sftp-password"));
        Assert.AreEqual(SecretOrigin.Stored, status.OriginOf("sftp-key-passphrase"));
        Assert.AreEqual(SecretOrigin.Stored, status.OriginOf("s3-secret-key:scans"));
        Assert.AreEqual(SecretOrigin.NotSet, status.OriginOf("s3-access-key:scans"));
        Assert.IsTrue(status.SftpPassword && status.SftpKeyPassphrase);
        Assert.IsTrue(status.S3["scans"].SecretKeySet);
        Assert.IsFalse(status.S3["scans"].AccessKeySet);
    }

    [TestMethod]
    public void A_stored_Secret_that_cannot_be_decrypted_is_reported_unreadable_and_not_used()
    {
        File.WriteAllText(MachinePath, ValidMachine().ToJsonString());
        Store("sftp-password", "from-store");

        var cfg = CreateWithStore(identity: new FixedIdentity("another-machine", "alice"));

        Assert.IsNull(cfg.LoadSecrets().SftpPassword);
        var status = cfg.Load().Secrets;
        Assert.AreEqual(SecretOrigin.Unreadable, status.OriginOf("sftp-password"));
        Assert.IsFalse(status.SftpPassword);
    }

    [TestMethod]
    public void Without_a_machine_identifier_the_environment_still_works_and_the_status_says_why()
    {
        File.WriteAllText(MachinePath, ValidMachine().ToJsonString());
        Store("sftp-password", "from-store");

        var cfg = CreateWithStore(new() { ["MIRES_SFTP_KEY_PASSPHRASE"] = "phrase-env" }, new FixedIdentity(null, "alice"));

        var secrets = cfg.LoadSecrets();
        Assert.IsNull(secrets.SftpPassword);
        Assert.AreEqual("phrase-env", secrets.SftpKeyPassphrase);
        var status = cfg.Load().Secrets;
        StringAssert.Contains(status.StoreProblem, "machine identifier");
        Assert.AreEqual(SecretOrigin.Environment, status.OriginOf("sftp-key-passphrase"));
    }

    [TestMethod]
    public void A_healthy_or_unconfigured_store_has_no_problem()
    {
        File.WriteAllText(MachinePath, ValidMachine().ToJsonString());
        Store("sftp-password", "from-store");

        Assert.IsNull(CreateWithStore().Load().Secrets.StoreProblem);
        Assert.IsNull(Create(ValidMachine().ToJsonString()).Load().Secrets.StoreProblem);
    }

    [TestMethod]
    public void A_stored_Secret_is_masked_in_logs()
    {
        File.WriteAllText(MachinePath, ValidMachine().ToJsonString());
        Store("sftp-password", "from-store-very-secret");

        var redactor = Redactor.From(CreateWithStore().LoadSecrets());

        Assert.AreEqual("auth failed with ***", redactor.Redact("auth failed with from-store-very-secret"));
    }

    [TestMethod]
    public void The_environment_wins_over_the_store()
    {
        File.WriteAllText(MachinePath, ValidMachine().ToJsonString());
        Store("sftp-password", "from-store");
        Store("s3-access-key:scans", "ak-store");
        Store("s3-secret-key:scans", "sk-store");

        var secrets = CreateWithStore(new() { ["MIRES_SFTP_PASSWORD"] = "from-env", ["MIRES_S3_SCANS_ACCESS_KEY"] = "ak-env" }).LoadSecrets();

        Assert.AreEqual("from-env", secrets.SftpPassword);
        Assert.AreEqual("ak-env", secrets.S3("scans")!.AccessKey);
        Assert.AreEqual("sk-store", secrets.S3("scans")!.SecretKey);
    }
}

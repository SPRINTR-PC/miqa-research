using System.Text.Json.Nodes;
using MiresSftpUploader.Core;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class ConfigurationSecretsTests : ConfigurationTestBase
{
    private const string Password = "hunter2-very-secret";

    [TestMethod]
    public void Secrets_come_only_from_their_fixed_environment_variables()
    {
        var cfg = Create(ValidMachine().ToJsonString(), env: new()
        {
            ["MIRES_SFTP_PASSWORD"] = Password,
            ["MIRES_SFTP_KEY_PASSPHRASE"] = "phrase",
            ["MIRES_S3_MY_BUCKET_ACCESS_KEY"] = "ak",
            ["MIRES_S3_MY_BUCKET_SECRET_KEY"] = "sk",
        });

        var secrets = cfg.LoadSecrets();

        Assert.AreEqual(Password, secrets.SftpPassword);
        Assert.AreEqual("phrase", secrets.SftpKeyPassphrase);
        Assert.AreEqual("ak", secrets.S3("my-bucket")!.AccessKey);
        Assert.AreEqual("sk", secrets.S3("My.Bucket")!.SecretKey);
        Assert.IsNull(secrets.S3("other"));
    }

    [TestMethod]
    public void A_secret_in_a_json_file_is_ignored_not_read()
    {
        var machine = ValidMachine();
        machine["Sftp"]!["Password"] = "from-file";
        var cfg = Create(machine.ToJsonString());

        Assert.IsNull(cfg.LoadSecrets().SftpPassword);
        var r = cfg.Load();
        Assert.IsFalse(r.Secrets.SftpPassword);
        Assert.IsTrue(r.Warnings.Any(w => w.Key == "Sftp:Password"));
        Assert.IsFalse(r.Warnings.Any(w => w.Message.Contains("from-file")));
    }

    [TestMethod]
    public void The_ui_view_says_only_set_or_not_set_and_the_secret_is_not_in_the_config()
    {
        var machine = ValidMachine();
        machine["Sources"] = new JsonArray(new JsonObject { ["Name"] = "my-bucket", ["Type"] = "S3", ["Endpoint"] = "https://s3.example.org", ["Bucket"] = "b" });
        var cfg = Create(machine.ToJsonString(), env: new()
        {
            ["MIRES_SFTP_PASSWORD"] = Password,
            ["MIRES_S3_MY_BUCKET_ACCESS_KEY"] = "ak",
        });

        var r = cfg.Load();

        Assert.IsTrue(r.Succeeded, string.Join(" | ", r.Errors));
        Assert.IsTrue(r.Secrets.SftpPassword);
        Assert.IsFalse(r.Secrets.SftpKeyPassphrase);
        Assert.IsTrue(r.Secrets.S3["my-bucket"].AccessKeySet);
        Assert.IsFalse(r.Secrets.S3["my-bucket"].SecretKeySet);
        var text = r.Config!.ToString() + r.Secrets + cfg.LoadSecrets() + string.Join("", r.Errors);
        Assert.IsFalse(text.Contains(Password));
        Assert.IsFalse(text.Contains("ak,"));
        Assert.IsFalse(cfg.LoadSecrets().ToString().Contains(Password));
    }

    [TestMethod]
    public void Secret_variables_never_leak_into_the_settings_layers()
    {
        var cfg = Create(ValidMachine().ToJsonString(), env: new()
        {
            ["MIRES_SFTP_PASSWORD"] = Password,
            ["MIRES_S3_A__B_ACCESS_KEY"] = "ak",
        });

        var r = cfg.Load();

        Assert.IsTrue(r.Succeeded, string.Join(" | ", r.Errors));
        Assert.AreEqual(ConfigLayer.Default, r.Setting("Sftp:Password").Layer);
        Assert.AreEqual(ConfigLayer.Default, r.Setting("S3").Layer);
    }
}

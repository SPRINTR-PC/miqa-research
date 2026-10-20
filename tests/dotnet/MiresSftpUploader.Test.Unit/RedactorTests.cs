using MiresSftpUploader.Core;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class RedactorTests : ConfigurationTestBase
{
    [TestMethod]
    public void Redactor_replaces_every_Secret_in_the_environment_wherever_it_appears()
    {
        var secrets = Create(ValidMachine().ToJsonString(), env: new()
        {
            ["MIRES_SFTP_PASSWORD"] = "hunter2-very-secret",
            ["MIRES_SFTP_KEY_PASSPHRASE"] = "phrase-xyz",
            ["MIRES_S3_SCANS_SECRET_KEY"] = "s3-secret/with+chars",
            ["MIRES_SFTP_HOST"] = "not-a-secret.example.org",
        }).LoadSecrets();
        var redactor = Redactor.From(secrets);

        var text = redactor.Redact("auth failed with hunter2-very-secret and again hunter2-very-secret; phrase-xyz; s3-secret/with+chars; host not-a-secret.example.org");

        Assert.AreEqual("auth failed with *** and again ***; ***; ***; host not-a-secret.example.org", text);
    }

    [TestMethod]
    public void Redactor_prefers_the_longer_Secret_when_one_contains_another()
    {
        var secrets = Create(ValidMachine().ToJsonString(), env: new()
        {
            ["MIRES_SFTP_PASSWORD"] = "abcd",
            ["MIRES_SFTP_KEY_PASSPHRASE"] = "abcdefgh",
        }).LoadSecrets();

        Assert.AreEqual("x *** y", Redactor.From(secrets).Redact("x abcdefgh y"));
    }

    [TestMethod]
    public void Redactor_without_Secrets_leaves_text_alone_and_tolerates_null()
    {
        var redactor = Redactor.From(Create(ValidMachine().ToJsonString()).LoadSecrets());

        Assert.AreEqual("nothing here", redactor.Redact("nothing here"));
        Assert.AreEqual("", redactor.Redact(null));
    }
}

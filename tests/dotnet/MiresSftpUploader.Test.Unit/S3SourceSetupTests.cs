using Amazon.Runtime;
using MiresSftpUploader.Core;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class S3SourceSetupTests
{
    private static SourceConfig S3Config(string name = "my-bucket") => new()
    {
        Name = name,
        Type = SourceType.S3,
        Endpoint = "https://s3.example.org:9000",
        Bucket = "scans",
        Prefix = "incoming",
        Region = "eu-north-1",
        ForcePathStyle = true,
    };

    private static Secrets SecretsOf(params (string Name, string Value)[] env) =>
        Secrets.FromEnvironment(env.ToDictionary(e => e.Name, e => (string?)e.Value));

    [TestMethod]
    public void The_client_uses_the_ServiceURL_and_path_style_and_calculates_and_validates_checksums_only_when_required()
    {
        var config = S3Source.CreateClientConfig(S3Config());

        Assert.AreEqual("https://s3.example.org:9000", config.ServiceURL?.TrimEnd('/'));
        Assert.IsTrue(config.ForcePathStyle);
        Assert.AreEqual(RequestChecksumCalculation.WHEN_REQUIRED, config.RequestChecksumCalculation);
        Assert.AreEqual(ResponseChecksumValidation.WHEN_REQUIRED, config.ResponseChecksumValidation);
        Assert.AreEqual("eu-north-1", config.AuthenticationRegion);
    }

    [TestMethod]
    public void An_S3_Source_is_built_from_its_config_with_credentials_from_its_secret_variables()
    {
        var secrets = SecretsOf(("MIRES_S3_MY_BUCKET_ACCESS_KEY", "ak"), ("MIRES_S3_MY_BUCKET_SECRET_KEY", "sk"));

        var source = SourceFactory.Create(S3Config(), secrets);

        Assert.IsInstanceOfType<S3Source>(source);
        Assert.AreEqual("my-bucket", source.Name);
    }

    [TestMethod]
    public void Missing_credentials_are_an_error_that_names_the_variables_and_never_falls_back_to_the_AWS_credential_chain()
    {
        var chain = SecretsOf(("AWS_ACCESS_KEY_ID", "chain"), ("AWS_SECRET_ACCESS_KEY", "chain"), ("MIRES_S3_MY_BUCKET_ACCESS_KEY", "ak"));

        var error = Assert.Throws<SourceSetupException>(() => SourceFactory.Create(S3Config(), chain));

        StringAssert.Contains(error.Message, "MIRES_S3_MY_BUCKET_ACCESS_KEY");
        StringAssert.Contains(error.Message, "MIRES_S3_MY_BUCKET_SECRET_KEY");
        Assert.DoesNotContain("chain", error.Message);
    }

    [TestMethod]
    public void A_Directory_config_gives_a_Directory_Source_with_its_Remote_Path()
    {
        var source = SourceFactory.Create(new SourceConfig { Name = "scans", Path = "/data/scans", RemotePath = "/custom" }, SecretsOf());

        Assert.IsInstanceOfType<DirectorySource>(source);
        Assert.AreEqual("/custom", source.RemotePath);
    }
}

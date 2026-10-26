using Microsoft.Extensions.Logging.Abstractions;
using MiresSftpUploader.Core;
using MiresSftpUploader.Test.Support;

namespace MiresSftpUploader.Test.Unit;

/// <summary>S3 Sources reach a Run through the production composition (window and Headless Run alike).</summary>
[TestClass]
public sealed class S3SourceCompositionTests : ConfigurationTestBase
{
    private string S3Machine()
    {
        var machine = ValidMachine();
        machine["State"] = new System.Text.Json.Nodes.JsonObject { ["Path"] = Path.Combine(Dir, "shared") };
        Directory.CreateDirectory(Path.Combine(Dir, "shared"));
        machine["Sources"] = System.Text.Json.Nodes.JsonNode.Parse("""
            [ { "Name": "my-bucket", "Type": "S3", "Endpoint": "http://127.0.0.1:1", "Bucket": "scans", "ForcePathStyle": true } ]
            """);
        return machine.ToJsonString();
    }

    private UploaderRuntime Runtime(Dictionary<string, string?> env, CliOptions cli)
    {
        File.WriteAllText(MachinePath, S3Machine());
        var configuration = new Configuration(new ConfigurationLocations(MachinePath, UserPath, env));
        return new UploaderRuntime(configuration, new StaticRemoteFactory(new FakeRemote()), NullLoggerFactory.Instance, TimeProvider.System, cli);
    }

    [TestMethod]
    public void The_default_source_factory_builds_an_S3_Source_from_its_secret_variables()
    {
        var secrets = Secrets.FromEnvironment(new Dictionary<string, string?>
        {
            ["MIRES_S3_MY_BUCKET_ACCESS_KEY"] = "ak", ["MIRES_S3_MY_BUCKET_SECRET_KEY"] = "sk",
        });
        var config = new SourceConfig { Name = "my-bucket", Type = SourceType.S3, Endpoint = "http://127.0.0.1:1", Bucket = "scans" };

        var source = new DefaultSourceFactory().Create(config, secrets);

        Assert.IsInstanceOfType<S3Source>(source);
    }

    [TestMethod]
    public void Preparing_with_an_S3_Source_whose_secrets_are_missing_gives_a_configuration_error_naming_the_variables_and_no_engine()
    {
        var cli = CliOptions.Parse(["--headless"]).Options!;

        var prepared = Runtime([], cli).Prepare(headless: true);

        Assert.IsNull(prepared.Engine);
        var text = string.Join("\n", prepared.Errors);
        StringAssert.Contains(text, "MIRES_S3_MY_BUCKET_ACCESS_KEY");
        StringAssert.Contains(text, "MIRES_S3_MY_BUCKET_SECRET_KEY");
    }

    [TestMethod]
    public async Task A_headless_run_with_missing_S3_secrets_exits_2_and_lists_the_variables_on_stderr()
    {
        var cli = CliOptions.Parse(["--headless"]).Options!;
        var stdout = new StringWriter();
        var stderr = new StringWriter();

        var exit = await HeadlessRunner.RunAsync(cli, Runtime([], cli), stdout, stderr, CancellationToken.None);

        Assert.AreEqual(2, exit);
        Assert.AreEqual("", stdout.ToString());
        StringAssert.Contains(stderr.ToString(), "MIRES_S3_MY_BUCKET_SECRET_KEY");
    }

    [TestMethod]
    public void Preparing_with_an_S3_Source_and_its_secrets_builds_an_engine()
    {
        var cli = CliOptions.Parse(["--headless"]).Options!;
        var env = new Dictionary<string, string?> { ["MIRES_S3_MY_BUCKET_ACCESS_KEY"] = "ak", ["MIRES_S3_MY_BUCKET_SECRET_KEY"] = "sk" };

        var prepared = Runtime(env, cli).Prepare(headless: true);

        Assert.IsEmpty(prepared.Errors);
        Assert.IsNotNull(prepared.Engine);
    }
}

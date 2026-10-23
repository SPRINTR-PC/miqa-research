using Microsoft.Extensions.Logging.Abstractions;
using MiresSftpUploader.Core;
using MiresSftpUploader.Test.Support;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class RunHistoryCliTests : ConfigurationTestBase
{
    private ConfigurationLocations Locations => new(MachinePath, UserPath, new Dictionary<string, string?>());

    private async Task<Guid> RecordOneRunAsync()
    {
        Directory.CreateDirectory(DataDir);
        File.WriteAllText(Path.Combine(DataDir, "a.txt"), "alpha");
        var machine = ValidMachine();
        machine["State"] = new System.Text.Json.Nodes.JsonObject
        {
            ["Path"] = Path.Combine(Dir, "shared"),
            ["AccessGroup"] = TestAccessGroup.Name,
        };
        File.WriteAllText(MachinePath, machine.ToJsonString());

        var cli = CliOptions.Parse(["--headless"]).Options!;
        var runtime = new UploaderRuntime(new Configuration(Locations), new StaticRemoteFactory(new FakeRemote()), NullLoggerFactory.Instance, TimeProvider.System, cli);
        var prepared = runtime.Prepare(headless: true);
        var result = await prepared.Engine!.RunAsync(new RunOptions(), new Progress<RunEvent>(), CancellationToken.None);
        return result.RunId;
    }

    [TestMethod]
    public async Task List_runs_and_export_run_read_the_Upload_State_found_from_the_configuration()
    {
        var runId = await RecordOneRunAsync();
        var state = UploaderComposition.LoadStateSettings(new Configuration(Locations), CliOptions.Parse(["--list-runs"]).Options!);

        var list = new StringWriter();
        Assert.IsTrue(Cli.TryRun(["--list-runs"], "1.0", list, new StringWriter(), out var listExit, Locations, state));
        var export = new StringWriter();
        Assert.IsTrue(Cli.TryRun(["--export-run", runId.ToString()], "1.0", export, new StringWriter(), out var exportExit, Locations, state));

        Assert.AreEqual(0, listExit);
        StringAssert.Contains(list.ToString(), runId.ToString());
        Assert.AreEqual(0, exportExit);
        StringAssert.Contains(export.ToString(), "a.txt");
    }

    [TestMethod]
    public void Without_a_Data_Directory_configured_the_default_one_is_used()
    {
        File.WriteAllText(MachinePath, ValidMachine().ToJsonString());

        var state = UploaderComposition.LoadStateSettings(new Configuration(Locations), new CliOptions());

        StringAssert.EndsWith(state!.Path, DataDirectory.DatabaseFileName);
    }
}

using System.Text.Json;
using Json.Schema;
using Microsoft.Extensions.Logging.Abstractions;
using MiresSftpUploader.Core;
using MiresSftpUploader.Test.Support;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class ManifestSchemaTests
{
    private static readonly JsonSchema Schema = JsonSchema.FromText(
        File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "shipped", "manifest.schema.json")));

    private static void AssertValid(string json)
    {
        var result = Schema.Evaluate(JsonDocument.Parse(json).RootElement, new EvaluationOptions { OutputFormat = OutputFormat.List });
        Assert.IsTrue(result.IsValid, "Manifest does not validate: " + JsonSerializer.Serialize(
            result.Details.Where(d => d.Errors is not null).SelectMany(d => d.Errors!.Select(e => $"{d.InstanceLocation}: {e.Value}"))));
    }

    private static async Task<string> ManifestAfterAsync(FakeRemote remote, EngineSettings settings, params ISource[] sources)
    {
        await new Engine(remote, sources, settings, NullLogger<Engine>.Instance, TimeProvider.System)
            .RunAsync(new RunOptions(), new Progress<RunEvent>(), CancellationToken.None);
        return remote.ReadText("/upload/scans/manifest.json");
    }

    private static EngineSettings Settings() => new()
    {
        RemoteRoot = "/upload",
        Retry = new RetrySettings { MaxAttempts = 1, BaseDelay = TimeSpan.Zero, MaxDelay = TimeSpan.Zero },
    };

    [TestMethod]
    public async Task A_complete_Manifest_with_nested_files_validates()
    {
        var source = new FakeSource("scans").Add("a.txt", "a").Add("sub/dir/b.txt", "b").Add("empty.bin", Array.Empty<byte>());
        AssertValid(await ManifestAfterAsync(new FakeRemote(), Settings(), source));
    }

    [TestMethod]
    public async Task A_Manifest_with_failures_and_deferred_files_validates()
    {
        var remote = new FakeRemote();
        remote.Inject(RemoteOperation.Upload, RemoteResult.Failed("disk full"), times: 3, pathContains: "bad.txt");
        var source = new FakeSource("scans").Add("good.txt", "g").Add("bad.txt", "b").Add("fresh.txt", "f", DateTimeOffset.UtcNow);
        var settings = Settings() with { Scan = new ScanConfig { MinFileAgeSeconds = 3600 } };
        AssertValid(await ManifestAfterAsync(remote, settings, source));
    }

    [TestMethod]
    public async Task A_Manifest_with_an_Archive_and_its_members_validates()
    {
        var source = new FakeSource("scans").Add("d/a.jpg", "alpha").Add("d/b.jpg", "beta").Add("d/c.txt", "gamma");
        var settings = Settings() with
        {
            Archive = new ArchiveConfig { MinFreeSpaceBytes = 0, Rules = [new ArchiveRuleConfig { Name = "tiles", Pattern = @"\.jpg$" }] },
        };
        var json = await ManifestAfterAsync(new FakeRemote(), settings, source);
        StringAssert.Contains(json, "\"archive\"");
        AssertValid(json);
    }

    [TestMethod]
    public void The_schema_rejects_a_Manifest_without_a_verdict()
    {
        var result = Schema.Evaluate(JsonDocument.Parse("""{"schemaVersion":1,"source":"s"}""").RootElement);
        Assert.IsFalse(result.IsValid);
    }
}

using System.Text.Json.Nodes;
using MiresSftpUploader.Core;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class ConfigurationSectionTests : ConfigurationTestBase
{
    [TestMethod]
    public void A_section_the_program_does_not_bind_is_available_as_flat_keys_with_environment_overrides_applied()
    {
        var machine = ValidMachine();
        machine["NLog"] = JsonNode.Parse("""
            { "variables": { "MinLevel": "Info" },
              "rules": { "10_file": { "logger": "*", "minLevel": "${var:MinLevel}", "writeTo": "file" } } }
            """);
        var cfg = Create(machine.ToJsonString(), env: new() { ["MIRES_NLog__variables__MinLevel"] = "Debug" });

        var section = cfg.Load().Section("NLog");

        Assert.AreEqual("Debug", section["variables:MinLevel"]);
        Assert.AreEqual("${var:MinLevel}", section["rules:10_file:minLevel"]);
        Assert.AreEqual("file", section["rules:10_file:writeTo"]);
    }

    [TestMethod]
    public void A_missing_section_is_empty()
    {
        Assert.IsEmpty(Create(ValidMachine().ToJsonString()).Load().Section("NLog"));
    }
}

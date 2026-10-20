using System.Text.Json.Nodes;
using MiresSftpUploader.Core;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class VerificationConfigurationTests : ConfigurationTestBase
{
    [TestMethod]
    public void Verification_defaults_are_off_with_sha256sum_and_a_one_hour_timeout()
    {
        var r = Create(ValidMachine().ToJsonString()).Load();

        Assert.IsTrue(r.Succeeded, string.Join(" | ", r.Errors));
        Assert.AreEqual(VerificationLevel.Off, r.Config!.Upload.VerifyAfterUpload);
        Assert.AreEqual(VerificationLevel.Off, r.Config.Upload.VerifyRemote);
        Assert.AreEqual("sha256sum -- {path}", r.Config.Upload.VerifyCommand);
        Assert.AreEqual(3600, r.Config.Upload.VerifyTimeoutSeconds);
    }

    [TestMethod]
    public void Verify_command_from_machine_config_is_used()
    {
        var machine = ValidMachine();
        machine["Upload"] = new JsonObject { ["VerifyCommand"] = "shasum -a 256 {path}" };

        var r = Create(machine.ToJsonString()).Load();

        Assert.AreEqual("shasum -a 256 {path}", r.Config!.Upload.VerifyCommand);
    }

    [TestMethod]
    public void Verify_command_from_the_environment_is_used()
    {
        var r = Create(ValidMachine().ToJsonString(), env: new() { ["MIRES_Upload__VerifyCommand"] = "shasum -a 256 {path}" }).Load();

        Assert.AreEqual("shasum -a 256 {path}", r.Config!.Upload.VerifyCommand);
    }

    [TestMethod]
    public void Verify_command_in_user_overrides_is_ignored_with_a_warning()
    {
        var user = """{ "ConfigVersion": 1, "Upload": { "VerifyCommand": "rm -rf / #{path}" } }""";

        var r = Create(ValidMachine().ToJsonString(), user).Load();

        Assert.IsTrue(r.Succeeded, string.Join(" | ", r.Errors));
        Assert.AreEqual("sha256sum -- {path}", r.Config!.Upload.VerifyCommand);
        Assert.IsTrue(r.Warnings.Any(w => w.Key == "Upload:VerifyCommand"));
    }

    [TestMethod]
    public void Verify_command_cannot_be_saved_from_the_ui()
    {
        var saved = Create(ValidMachine().ToJsonString()).Save(new Dictionary<string, string?> { ["Upload:VerifyCommand"] = "echo {path}" });

        Assert.IsFalse(saved.Succeeded);
        Assert.IsTrue(saved.Errors.Any(e => e.Key == "Upload:VerifyCommand"));
        Assert.IsFalse(File.Exists(UserPath));
    }

    [TestMethod]
    public void Verify_command_without_a_path_placeholder_is_an_error()
    {
        var machine = ValidMachine();
        machine["Upload"] = new JsonObject { ["VerifyCommand"] = "sha256sum /etc/passwd" };

        var r = Create(machine.ToJsonString()).Load();

        Assert.IsTrue(r.Errors.Any(e => e.Key == "Upload:VerifyCommand"));
    }

    [TestMethod]
    public void Verification_level_can_be_saved_by_a_user()
    {
        var cfg = Create(ValidMachine().ToJsonString());

        var saved = cfg.Save(new Dictionary<string, string?> { ["Upload:VerifyAfterUpload"] = "Hash" });

        Assert.IsTrue(saved.Succeeded, string.Join(" | ", saved.Errors));
        Assert.AreEqual(VerificationLevel.Hash, cfg.Load().Config!.Upload.VerifyAfterUpload);
    }
}

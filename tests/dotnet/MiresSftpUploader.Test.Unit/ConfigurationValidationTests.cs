using System.Text.Json.Nodes;
using MiresSftpUploader.Core;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class ConfigurationValidationTests : ConfigurationTestBase
{
    private LoadResult Load(JsonObject json, bool headless = false, Dictionary<string, string?>? env = null) =>
        Create(json.ToJsonString(), env: env).Load(headless: headless);

    private static void AssertError(LoadResult r, string key, string? messagePart = null)
    {
        Assert.IsNull(r.Config, "an invalid configuration yields no AppConfig");
        var hit = r.Errors.FirstOrDefault(e => string.Equals(e.Key, key, StringComparison.OrdinalIgnoreCase));
        Assert.IsNotNull(hit, $"expected an error for {key}; got: {string.Join(" | ", r.Errors)}");
        if (messagePart is not null) StringAssert.Contains(hit.Message, messagePart);
    }

    [TestMethod]
    public void A_complete_valid_configuration_has_no_errors()
    {
        var r = Load(ValidMachine());

        Assert.IsTrue(r.Succeeded, string.Join(" | ", r.Errors));
        Assert.AreEqual("abc", r.Config!.Sftp.HostKeyFingerprint);
    }

    [TestMethod]
    public void Every_error_is_reported_together()
    {
        var json = ValidMachine();
        json["Sftp"]!["Host"] = "";
        json["Upload"] = new JsonObject { ["MaxParallelUploads"] = 99 };
        json["Ignore"] = new JsonObject { ["Patterns"] = new JsonArray("([") };

        var r = Load(json);

        AssertError(r, "Sftp:Host");
        AssertError(r, "Upload:MaxParallelUploads");
        AssertError(r, "Ignore:Patterns:0");
    }

    [TestMethod]
    public void Required_fields_are_host_username_fingerprint_and_at_least_one_enabled_source()
    {
        var r = Create("{}").Load();

        AssertError(r, "Sftp:Host");
        AssertError(r, "Sftp:Username");
        AssertError(r, "Sftp:HostKeyFingerprint");
        AssertError(r, "Sources");
    }

    [TestMethod]
    public void Host_key_fingerprint_prefixes_are_normalised_away()
    {
        var json = ValidMachine();
        json["Sftp"]!["HostKeyFingerprint"] = "SHA256:AbCd+/=";

        Assert.AreEqual("AbCd+/=", Load(json).Config!.Sftp.HostKeyFingerprint);
    }

    [TestMethod]
    public void Private_key_authentication_needs_a_key_path()
    {
        var json = ValidMachine();
        json["Sftp"]!["AuthMethod"] = "PrivateKey";

        AssertError(Load(json), "Sftp:PrivateKeyPath");
    }

    [TestMethod]
    public void An_unknown_enum_value_is_an_error_naming_the_choices()
    {
        var json = ValidMachine();
        json["Ui"] = new JsonObject { ["Theme"] = "Purple" };

        AssertError(Load(json), "Ui:Theme", "Dark");
    }

    [TestMethod]
    [DataRow("Upload", "MaxParallelUploads", 0)]
    [DataRow("Upload", "MaxParallelUploads", 17)]
    [DataRow("Retry", "MaxAttempts", -1)]
    [DataRow("Retry", "MaxAttempts", 11)]
    [DataRow("Sftp", "Port", 0)]
    [DataRow("Sftp", "Port", 70000)]
    [DataRow("Sftp", "ConnectTimeoutSeconds", 0)]
    [DataRow("Scan", "MinFileAgeSeconds", -5)]
    [DataRow("Logging", "RetainDays", -1)]
    public void Numbers_outside_their_range_are_errors(string section, string key, int value)
    {
        var json = ValidMachine();
        json[section] = new JsonObject { [key] = value };

        AssertError(Load(json), $"{section}:{key}");
    }

    [TestMethod]
    public void Range_boundaries_are_accepted()
    {
        var json = ValidMachine();
        json["Upload"] = new JsonObject { ["MaxParallelUploads"] = 16 };
        json["Retry"] = new JsonObject { ["MaxAttempts"] = 0 };
        json["Sftp"]!["Port"] = 65535;

        Assert.IsTrue(Load(json).Succeeded);
    }

    [TestMethod]
    public void Retry_base_delay_cannot_exceed_max_delay()
    {
        var json = ValidMachine();
        json["Retry"] = new JsonObject { ["BaseDelaySeconds"] = 90, ["MaxDelaySeconds"] = 60 };

        AssertError(Load(json), "Retry:BaseDelaySeconds");
    }

    [TestMethod]
    public void Regexes_that_do_not_compile_are_errors_wherever_they_appear()
    {
        var json = ValidMachine();
        json["Ignore"] = new JsonObject { ["Patterns"] = new JsonArray("ok", "([") };
        json["Archive"] = new JsonObject { ["Rules"] = new JsonArray(new JsonObject { ["Name"] = "r", ["Pattern"] = "(" }) };
        json["Sources"]![0]!["Ignore"] = new JsonObject { ["Patterns"] = new JsonArray("*bad") };
        json["Sources"]![0]!["ArchiveRules"] = new JsonArray(new JsonObject { ["Name"] = "r2", ["Pattern"] = "[" });

        var r = Load(json);

        AssertError(r, "Ignore:Patterns:1");
        AssertError(r, "Archive:Rules:0:Pattern");
        AssertError(r, "Sources:0:Ignore:Patterns:0");
        AssertError(r, "Sources:0:ArchiveRules:0:Pattern");
    }

    [TestMethod]
    public void An_archive_rule_needs_a_pattern_and_names_must_be_unique()
    {
        var json = ValidMachine();
        json["Archive"] = new JsonObject
        {
            ["Rules"] = new JsonArray(
                new JsonObject { ["Name"] = "dup", ["Pattern"] = "a" },
                new JsonObject { ["Name"] = "DUP", ["Pattern"] = "b" },
                new JsonObject { ["Name"] = "empty" }),
        };

        var r = Load(json);

        AssertError(r, "Archive:Rules:1:Name", "unique");
        AssertError(r, "Archive:Rules:2:Pattern");
    }

    [TestMethod]
    public void Source_names_must_be_unique_and_filename_safe()
    {
        var json = ValidMachine();
        var path = DataDir;
        json["Sources"] = new JsonArray(
            new JsonObject { ["Name"] = "alpha", ["Path"] = path },
            new JsonObject { ["Name"] = "ALPHA", ["Path"] = path },
            new JsonObject { ["Name"] = "a/b", ["Path"] = path },
            new JsonObject { ["Name"] = "..", ["Path"] = path },
            new JsonObject { ["Path"] = path });

        var r = Load(json);

        AssertError(r, "Sources:1:Name", "unique");
        AssertError(r, "Sources:2:Name", "filename");
        AssertError(r, "Sources:3:Name", "filename");
        AssertError(r, "Sources:4:Name");
    }

    [TestMethod]
    [DataRow("relative/path")]
    [DataRow("/a/../b")]
    [DataRow("C:\\windows")]
    [DataRow("/a\\b")]
    public void Remote_paths_must_be_absolute_posix_without_dot_dot(string remotePath)
    {
        var json = ValidMachine();
        json["Sources"]![0]!["RemotePath"] = remotePath;
        json["Sftp"]!["RemoteRoot"] = remotePath;

        var r = Load(json);

        AssertError(r, "Sources:0:RemotePath");
        AssertError(r, "Sftp:RemoteRoot");
    }

    [TestMethod]
    public void An_absolute_posix_remote_path_is_accepted()
    {
        var json = ValidMachine();
        json["Sources"]![0]!["RemotePath"] = "/incoming/alpha";

        Assert.IsTrue(Load(json).Succeeded);
    }

    [TestMethod]
    public void A_directory_source_needs_a_path_and_an_s3_source_needs_endpoint_and_bucket()
    {
        var json = ValidMachine();
        json["Sources"] = new JsonArray(
            new JsonObject { ["Name"] = "d" },
            new JsonObject { ["Name"] = "s", ["Type"] = "S3" });

        var r = Load(json);

        AssertError(r, "Sources:0:Path");
        AssertError(r, "Sources:1:Endpoint");
        AssertError(r, "Sources:1:Bucket");
    }

    [TestMethod]
    public void A_missing_directory_is_a_warning_in_the_ui_and_an_error_when_headless()
    {
        var json = ValidMachine();
        json["Sources"]![0]!["Path"] = Path.Combine(Dir, "does-not-exist");

        var ui = Load(json, headless: false);
        var headless = Load(json, headless: true);

        Assert.IsTrue(ui.Succeeded);
        Assert.AreEqual(1, ui.Warnings.Count);
        AssertError(headless, "Sources:0:Path", "exist");
    }

    [TestMethod]
    public void A_disabled_source_is_not_checked_for_its_directory_but_cannot_be_the_only_source()
    {
        var json = ValidMachine();
        json["Sources"]![0]!["Enabled"] = false;
        json["Sources"]![0]!["Path"] = Path.Combine(Dir, "does-not-exist");

        var r = Load(json, headless: true);

        Assert.AreEqual(0, r.Warnings.Count);
        AssertError(r, "Sources", "enabled");
    }

    [TestMethod]
    public void Manifest_names_must_not_collide()
    {
        var json = ValidMachine();
        json["Manifest"] = new JsonObject { ["JsonName"] = "m.json", ["FlatName"] = "M.JSON", ["InProgressSuffix"] = "" };

        var r = Load(json);

        AssertError(r, "Manifest:FlatName", "collide");
        AssertError(r, "Manifest:InProgressSuffix");
    }

    [TestMethod]
    public void Manifest_names_must_be_plain_file_names()
    {
        var json = ValidMachine();
        json["Manifest"] = new JsonObject { ["JsonName"] = "sub/manifest.json" };

        AssertError(Load(json), "Manifest:JsonName");
    }

    [TestMethod]
    public void Colliding_normalised_s3_secret_names_are_an_error()
    {
        var json = ValidMachine();
        json["Sources"] = new JsonArray(
            new JsonObject { ["Name"] = "my-bucket", ["Type"] = "S3", ["Endpoint"] = "https://s3.example.org", ["Bucket"] = "b1" },
            new JsonObject { ["Name"] = "my_bucket", ["Type"] = "S3", ["Endpoint"] = "https://s3.example.org", ["Bucket"] = "b2" });

        var r = Load(json);

        AssertError(r, "Sources:1:Name", "MY_BUCKET");
    }

    [TestMethod]
    public void Verification_conflicts_with_write_only_access()
    {
        var json = ValidMachine();
        json["Sftp"]!["RemoteAccess"] = "WriteOnly";
        json["Upload"] = new JsonObject { ["VerifyAfterUpload"] = "Hash", ["VerifyRemote"] = "Size" };

        var r = Load(json);

        AssertError(r, "Upload:VerifyAfterUpload", "WriteOnly");
        AssertError(r, "Upload:VerifyRemote", "WriteOnly");
    }

    [TestMethod]
    public void Verification_is_fine_when_the_server_is_readable()
    {
        var json = ValidMachine();
        json["Upload"] = new JsonObject { ["VerifyAfterUpload"] = "ReadBack" };

        Assert.IsTrue(Load(json).Succeeded);
    }

    [TestMethod]
    public void A_move_target_overlapping_its_source_directory_is_an_error()
    {
        var json = ValidMachine();
        var src = Path.Combine(Dir, "src");
        Directory.CreateDirectory(src);
        json["Sources"] = new JsonArray(new JsonObject
        {
            ["Name"] = "alpha",
            ["Path"] = src,
            ["AfterUpload"] = new JsonObject
            {
                ["OnSuccess"] = new JsonObject { ["Action"] = "Move", ["Path"] = Path.Combine(src, "done") },
                ["OnFailure"] = new JsonObject { ["Action"] = "Move", ["Path"] = Dir },
            },
        });

        var r = Load(json);

        AssertError(r, "Sources:0:AfterUpload:OnSuccess:Path", "overlap");
        AssertError(r, "Sources:0:AfterUpload:OnFailure:Path", "overlap");
    }

    [TestMethod]
    public void A_move_target_beside_the_source_is_accepted_and_needs_a_path()
    {
        var json = ValidMachine();
        var src = Path.Combine(Dir, "src");
        Directory.CreateDirectory(src);
        json["Sources"] = new JsonArray(new JsonObject
        {
            ["Name"] = "alpha",
            ["Path"] = src,
            ["AfterUpload"] = new JsonObject
            {
                ["OnSuccess"] = new JsonObject { ["Action"] = "Move", ["Path"] = Path.Combine(Dir, "src-done") },
                ["OnFailure"] = new JsonObject { ["Action"] = "Move" },
            },
        });

        var r = Load(json);

        Assert.AreEqual(1, r.Errors.Count, string.Join(" | ", r.Errors));
        AssertError(r, "Sources:0:AfterUpload:OnFailure:Path");
    }

    [TestMethod]
    public void An_s3_move_target_under_the_source_prefix_is_an_error_but_a_sibling_prefix_is_not()
    {
        var json = ValidMachine();
        json["Sources"] = new JsonArray(new JsonObject
        {
            ["Name"] = "s",
            ["Type"] = "S3",
            ["Endpoint"] = "https://s3.example.org",
            ["Bucket"] = "b",
            ["Prefix"] = "in/",
            ["AfterUpload"] = new JsonObject
            {
                ["OnSuccess"] = new JsonObject { ["Action"] = "Move", ["Bucket"] = "b", ["Prefix"] = "in/done/" },
                ["OnFailure"] = new JsonObject { ["Action"] = "Move", ["Bucket"] = "b", ["Prefix"] = "failed/" },
            },
        });

        var r = Load(json);

        AssertError(r, "Sources:0:AfterUpload:OnSuccess:Prefix", "overlap");
        Assert.AreEqual(1, r.Errors.Count, string.Join(" | ", r.Errors));
    }
}

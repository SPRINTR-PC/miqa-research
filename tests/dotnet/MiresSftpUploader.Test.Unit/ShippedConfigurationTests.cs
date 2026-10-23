using System.Text.RegularExpressions;
using MiresSftpUploader.Core;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class ShippedConfigurationTests : ConfigurationTestBase
{
    private static string Shipped => Path.Combine(AppContext.BaseDirectory, "shipped", "appsettings.json");

    [TestMethod]
    public void The_shipped_appsettings_validates_except_for_the_documented_required_fields()
    {
        var cfg = new Configuration(new ConfigurationLocations(Shipped, UserPath, new Dictionary<string, string?>()));

        var r = cfg.Load();

        CollectionAssert.AreEquivalent(
            new[] { "Sftp:Host", "Sftp:Username", "Sftp:HostKeyFingerprint", "Sources" },
            r.Errors.Select(e => e.Key!).ToArray());
    }

    [TestMethod]
    public void Supplying_the_required_fields_makes_the_shipped_appsettings_valid_with_dark_theme_by_default()
    {
        var env = new Dictionary<string, string?>
        {
            ["MIRES_Sftp__Host"] = "sftp.example.org",
            ["MIRES_Sftp__Username"] = "u",
            ["MIRES_Sftp__HostKeyFingerprint"] = "fp",
            ["MIRES_Sources__0__Name"] = "alpha",
            ["MIRES_Sources__0__Path"] = Dir,
        };

        var r = new Configuration(new ConfigurationLocations(Shipped, UserPath, env)).Load();

        Assert.IsTrue(r.Succeeded, string.Join(" | ", r.Errors));
        Assert.AreEqual(UiTheme.Dark, r.Config!.Ui.Theme);
    }

    [TestMethod]
    public void The_shipped_appsettings_has_no_host_sources_or_secrets()
    {
        var keys = Regex.Matches(File.ReadAllText(Shipped), "\"(\\w+)\"\\s*:").Select(m => m.Groups[1].Value).ToList();

        foreach (var forbidden in new[] { "Sources", "Host", "Username", "HostKeyFingerprint", "Password", "KeyPassphrase", "AccessKey", "SecretKey" })
            CollectionAssert.DoesNotContain(keys, forbidden);
    }
}

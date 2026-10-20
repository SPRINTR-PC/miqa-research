using MiresSftpUploader.Core;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class HostKeyFingerprintTests
{
    private const string Sha256 = "nThbg6kXUpJWGl7E1IGOCspRomTxdCARLviKw6E5SY8";
    private const string Md5 = "9b:3f:00:a1:7c:de:12:45:67:89:ab:cd:ef:01:23:45";

    [TestMethod]
    [DataRow(Sha256)]
    [DataRow("SHA256:" + Sha256)]
    [DataRow("sha256:" + Sha256)]
    [DataRow("  SHA256:" + Sha256 + "=  ")]
    public void Sha256_fingerprint_matches_with_or_without_prefix(string configured)
    {
        Assert.IsTrue(HostKeyFingerprint.Matches(configured, Sha256, Md5));
    }

    [TestMethod]
    [DataRow(Md5)]
    [DataRow("MD5:" + Md5)]
    [DataRow("md5:9B:3F:00:A1:7C:DE:12:45:67:89:AB:CD:EF:01:23:45")]
    public void Md5_fingerprint_matches_ignoring_case_and_prefix(string configured)
    {
        Assert.IsTrue(HostKeyFingerprint.Matches(configured, Sha256, Md5));
    }

    [TestMethod]
    public void Sha256_comparison_is_case_sensitive()
    {
        Assert.IsFalse(HostKeyFingerprint.Matches(Sha256.ToLowerInvariant(), Sha256, Md5));
    }

    [TestMethod]
    [DataRow("")]
    [DataRow("SHA256:AAAA")]
    [DataRow("MD5:00:11")]
    public void Different_or_empty_fingerprint_does_not_match(string configured)
    {
        Assert.IsFalse(HostKeyFingerprint.Matches(configured, Sha256, Md5));
    }
}

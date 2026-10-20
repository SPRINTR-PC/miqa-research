using MiresSftpUploader.Core;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class VerifyCommandTests
{
    [TestMethod]
    public void Default_template_shell_quotes_the_path()
    {
        var command = VerifyCommand.Build(UploadConfig.DefaultVerifyCommand, "/upload/my scans/a'b.txt.part");

        Assert.AreEqual("sha256sum -- '/upload/my scans/a'\\''b.txt.part'", command);
    }

    [TestMethod]
    public void Template_without_a_path_placeholder_is_refused()
    {
        Assert.IsFalse(VerifyCommand.IsValidTemplate("sha256sum /etc/passwd"));
        Assert.IsTrue(VerifyCommand.IsValidTemplate("shasum -a 256 {path}"));
    }

    [TestMethod]
    public void Hash_is_the_first_64_hex_characters_of_the_output()
    {
        var hash = new string('A', 64);

        Assert.AreEqual(new string('a', 64), VerifyCommand.ParseHash($"{hash}  /some/file\n"));
        Assert.IsNull(VerifyCommand.ParseHash("sha256sum: /x: No such file or directory"));
        Assert.IsNull(VerifyCommand.ParseHash(new string('a', 63)));
    }
}

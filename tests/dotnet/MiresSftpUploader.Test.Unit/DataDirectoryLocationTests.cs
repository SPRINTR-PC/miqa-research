using MiresSftpUploader.Core;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class DataDirectoryLocationTests
{
    [TestMethod]
    [DataRow(DataDirectoryPlatform.Windows, @"C:\ProgramData", "MiresSftpUploader")]
    [DataRow(DataDirectoryPlatform.Linux, "", "/var/lib/mires-sftp-uploader")]
    [DataRow(DataDirectoryPlatform.MacOS, "", "/Users/Shared/MiresSftpUploader")]
    public void Default_Data_Directory_is_per_operating_system(DataDirectoryPlatform platform, string commonAppData, string expectedEnd)
    {
        var path = DataDirectory.Resolve(flag: null, environment: null, platform, commonAppData);

        Assert.IsTrue(path.EndsWith(expectedEnd, StringComparison.Ordinal), path);
        if (platform == DataDirectoryPlatform.Windows) StringAssert.StartsWith(path, commonAppData);
    }

    [TestMethod]
    public void Environment_variable_overrides_the_default()
    {
        var path = DataDirectory.Resolve(null, "/srv/mires", DataDirectoryPlatform.Linux, "");

        Assert.AreEqual("/srv/mires", path);
    }

    [TestMethod]
    public void Command_line_flag_overrides_the_environment_variable()
    {
        var path = DataDirectory.Resolve("/opt/state", "/srv/mires", DataDirectoryPlatform.Linux, "");

        Assert.AreEqual("/opt/state", path);
    }

    [TestMethod]
    public void Database_lives_inside_the_Data_Directory()
    {
        Assert.AreEqual(Path.Combine("/srv/mires", "upload-state.db"), DataDirectory.DatabasePath("/srv/mires"));
    }
}

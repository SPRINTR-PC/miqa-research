using MiresSftpUploader.Core;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class UserSettingsTests : ConfigurationTestBase
{
    [TestMethod]
    public void Saving_the_theme_writes_it_to_User_Overrides_and_the_next_load_uses_it()
    {
        var configuration = Create(ValidMachine().ToJsonString());

        var error = UserSettings.SaveTheme(configuration, UiTheme.Light);

        Assert.IsNull(error);
        Assert.AreEqual(UiTheme.Light, configuration.Load().Config!.Ui.Theme);
        StringAssert.Contains(File.ReadAllText(UserPath), "Light");
    }

    [TestMethod]
    public void A_theme_set_by_the_environment_is_locked_and_reports_why()
    {
        var configuration = Create(ValidMachine().ToJsonString(), env: new() { ["MIRES_Ui__Theme"] = "Dark" });

        var error = UserSettings.SaveTheme(configuration, UiTheme.Light);

        StringAssert.Contains(error, "Locked Setting");
        Assert.IsFalse(File.Exists(UserPath));
    }
}

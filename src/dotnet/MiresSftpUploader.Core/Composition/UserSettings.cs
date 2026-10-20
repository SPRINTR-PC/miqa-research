namespace MiresSftpUploader.Core;

/// <summary>Settings the window changes on its own and saves to User Overrides.</summary>
public static class UserSettings
{
    /// <summary>Saves <c>Ui:Theme</c>; returns null on success, otherwise why it could not be saved (for example a Locked Setting).</summary>
    public static string? SaveTheme(Configuration configuration, UiTheme theme)
    {
        var saved = configuration.Save(new Dictionary<string, string?> { ["Ui:Theme"] = theme.ToString() });
        return saved.Succeeded ? null : string.Join(" ", saved.Errors.Select(e => e.ToString()));
    }
}

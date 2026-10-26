namespace MiresSftpUploader.Core;

public enum DataDirectoryPlatform { Windows, Linux, MacOS }

/// <summary>
/// Where the Data Directory is: the per-OS default, overridable by <c>MIRES_DATA_DIR</c> and then by <c>--data-dir</c>.
/// </summary>
public static partial class DataDirectory
{
    public const string EnvironmentVariable = "MIRES_DATA_DIR";
    public const string DatabaseFileName = "upload-state.db";

    public static DataDirectoryPlatform CurrentPlatform =>
        OperatingSystem.IsWindows() ? DataDirectoryPlatform.Windows
        : OperatingSystem.IsMacOS() ? DataDirectoryPlatform.MacOS
        : DataDirectoryPlatform.Linux;

    /// <summary>Command-line flag beats environment variable beats the OS default.</summary>
    public static string Resolve(string? flag, string? environment, DataDirectoryPlatform platform, string commonAppData)
    {
        if (!string.IsNullOrWhiteSpace(flag)) return flag;
        if (!string.IsNullOrWhiteSpace(environment)) return environment;
        return platform switch
        {
            DataDirectoryPlatform.Windows => Path.Combine(commonAppData, "MiresSftpUploader"),
            DataDirectoryPlatform.MacOS => "/Users/Shared/MiresSftpUploader",
            _ => "/var/lib/mires-sftp-uploader",
        };
    }

    /// <summary>The Upload State database inside a Data Directory; the lock file lives beside it.</summary>
    public static string DatabasePath(string dataDirectory) => Path.Combine(dataDirectory, DatabaseFileName);
}

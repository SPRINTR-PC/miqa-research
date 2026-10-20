namespace MiresSftpUploader.Core;

/// <summary>
/// The answer to "can this account use the Data Directory": shown in Settings next to State:Path and reported at each Run start.
/// <see cref="Problem"/> is null when all is well; otherwise it is the message for the banner or the Headless Run's stderr.
/// </summary>
public sealed record DataDirectoryAccess(
    string Path,
    bool Exists,
    bool Writable,
    string Account,
    string? Group,
    long DatabaseSizeBytes,
    long FreeSpaceBytes,
    bool OnNetworkShare,
    string FixCommand,
    string? Problem);

public static partial class DataDirectory
{
    /// <summary>Checks the directory by actually creating and removing a probe file, which is the only reliable test of ACLs, groups and read-only mounts.</summary>
    public static DataDirectoryAccess Check(string path, DataDirectoryPlatform? platform = null)
    {
        platform ??= CurrentPlatform;
        var account = Environment.UserName;
        var fix = FixCommand(path, platform.Value);
        var exists = Directory.Exists(path);

        string? problem = null;
        var writable = false;
        if (!exists)
        {
            problem = $"The Data Directory '{path}' does not exist. Account '{account}' cannot use the Upload State. Ask an administrator to run: {fix}";
        }
        else
        {
            writable = TryWriteProbe(path);
            if (!writable)
                problem = $"The Data Directory '{path}' is not writable by account '{account}'. Ask an administrator to run: {fix}";
        }

        return new DataDirectoryAccess(
            path, exists, writable, account,
            exists ? GroupOf(path) : null,
            exists ? DatabaseSize(path) : 0,
            exists ? FreeSpace(path) : 0,
            exists && IsNetworkShare(path),
            fix, problem);
    }

    private static bool TryWriteProbe(string directory)
    {
        var probe = System.IO.Path.Combine(directory, $".access-check-{Guid.NewGuid():N}");
        try
        {
            File.WriteAllText(probe, "x");
            File.Delete(probe);
            return true;
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            return false;
        }
    }

    private static long DatabaseSize(string directory)
    {
        var database = DatabasePath(directory);
        long total = 0;
        foreach (var file in new[] { database, database + "-wal" })
            if (File.Exists(file)) total += new FileInfo(file).Length;
        return total;
    }

    /// <summary>Free space on the volume that holds <paramref name="path"/>, or on its nearest existing parent when it does not exist yet; 0 when unknown.</summary>
    public static long FreeSpaceBytes(string path)
    {
        var probe = System.IO.Path.GetFullPath(path);
        while (!Directory.Exists(probe) && System.IO.Path.GetDirectoryName(probe) is { } parent) probe = parent;
        return FreeSpace(probe);
    }

    private static long FreeSpace(string path)
    {
        try
        {
            lock (DriveLock) return DriveFor(path)?.AvailableFreeSpace ?? 0;
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            return 0;
        }
    }

    /// <summary>Detection is a best effort (Windows UNC paths and network drives, Unix network mounts); a miss only costs a warning.</summary>
    public static bool IsNetworkShare(string path)
    {
        var full = System.IO.Path.GetFullPath(path);
        if (full.StartsWith(@"\\", StringComparison.Ordinal)) return true;
        try
        {
            lock (DriveLock) return DriveFor(full)?.DriveType == DriveType.Network;
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            return false;
        }
    }

    // DriveInfo.GetDrives uses getmntinfo on macOS, whose static buffer is not thread-safe: parallel callers crashed the process.
    private static readonly object DriveLock = new();

    private static DriveInfo? DriveFor(string path)
    {
        var full = System.IO.Path.GetFullPath(path);
        return DriveInfo.GetDrives()
            .Where(d => full.StartsWith(d.RootDirectory.FullName, StringComparison.Ordinal))
            .OrderByDescending(d => d.RootDirectory.FullName.Length)
            .FirstOrDefault();
    }
}

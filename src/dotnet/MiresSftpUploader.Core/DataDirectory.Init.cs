using System.Diagnostics;
using System.Runtime.Versioning;
using System.Security.AccessControl;
using System.Security.Principal;

namespace MiresSftpUploader.Core;

/// <summary>What <see cref="DataDirectory.Initialize"/> did: the steps taken (also when nothing needed changing), or why it could not.</summary>
public sealed record DataDirectoryInitResult(bool Ok, IReadOnlyList<string> Actions, string? Error);

public static partial class DataDirectory
{
    /// <summary>Directory mode for Linux and macOS: rwx for owner and group, nothing for others, setgid so new entries inherit the group.</summary>
    internal const UnixFileMode DirectoryMode = UnixFileMode.SetGroup
        | UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute
        | UnixFileMode.GroupRead | UnixFileMode.GroupWrite | UnixFileMode.GroupExecute;

    /// <summary>Mode of every file the app creates in the Data Directory. SQLite gives -wal and -shm the database file's mode.</summary>
    internal const UnixFileMode FileMode = UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.GroupRead | UnixFileMode.GroupWrite;

    /// <summary>The group that is granted access unless <c>State:AccessGroup</c> says otherwise. Windows uses BUILTIN\Users instead.</summary>
    public static string DefaultGroup(DataDirectoryPlatform platform) =>
        platform == DataDirectoryPlatform.MacOS ? "staff" : "mires-uploader";

    /// <summary>The command an administrator runs to create or repair the Data Directory.</summary>
    public static string FixCommand(string path, DataDirectoryPlatform platform) =>
        platform == DataDirectoryPlatform.Windows
            ? $"MiresSftpUploader.exe --init-data-dir --data-dir \"{path}\"   (run from an elevated prompt)"
            : $"sudo MiresSftpUploader --init-data-dir --data-dir '{path}'";

    /// <summary>
    /// Creates or repairs the Data Directory so every account in the access group can use it. Safe to run again.
    /// Windows: inheritable Modify for BUILTIN\Users. Linux and macOS: group <paramref name="group"/> (default
    /// mires-uploader / staff), mode 2770 (setgid), existing contents repaired to the group and 0660/2770.
    /// A missing group is reported, never created.
    /// </summary>
    public static DataDirectoryInitResult Initialize(string path, string? group, DataDirectoryPlatform platform)
    {
        var actions = new List<string>();
        try
        {
            if (platform == DataDirectoryPlatform.Windows) return InitializeWindows(path, actions);
            if (OperatingSystem.IsWindows()) throw new PlatformNotSupportedException();
            return InitializeUnix(path, group ?? DefaultGroup(platform), platform, actions);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or InvalidOperationException)
        {
            return new DataDirectoryInitResult(false, actions, $"Could not set up '{path}' for {Environment.UserName}: {ex.Message}");
        }
    }

    [UnsupportedOSPlatform("windows")]
    private static DataDirectoryInitResult InitializeUnix(string path, string group, DataDirectoryPlatform platform, List<string> actions)
    {
        if (GroupExists(group, platform) == false)
        {
            var create = platform == DataDirectoryPlatform.Linux ? $" Create it first: sudo groupadd {group}" : "";
            return new DataDirectoryInitResult(false, actions, $"Group '{group}' does not exist on this machine.{create}");
        }

        var created = !Directory.Exists(path);
        if (created)
        {
            Directory.CreateDirectory(path);
            actions.Add($"Created {path}");
        }

        try
        {
            Repair(path, group, DirectoryMode, actions);
            foreach (var entry in Directory.EnumerateFileSystemEntries(path, "*", SearchOption.AllDirectories))
                Repair(entry, group, Directory.Exists(entry) ? DirectoryMode : FileMode, actions);
        }
        catch
        {
            if (created) TryDeleteEmpty(path);
            throw;
        }

        return new DataDirectoryInitResult(true, actions, null);
    }

    [UnsupportedOSPlatform("windows")]
    private static void Repair(string entry, string group, UnixFileMode mode, List<string> actions)
    {
        if (!string.Equals(GroupOf(entry), group, StringComparison.Ordinal))
        {
            var (code, output) = Run("chgrp", group, entry);
            if (code != 0) throw new IOException($"chgrp {group} failed: {output}");
            actions.Add($"Group of {entry} set to {group}");
        }

        if (File.GetUnixFileMode(entry) != mode)
        {
            File.SetUnixFileMode(entry, mode);
            if (File.GetUnixFileMode(entry) != mode)
                throw new IOException($"Could not set mode {Convert.ToString((int)mode, 8)} on {entry}; the account must own it and be in group {group}");
            actions.Add($"Mode of {entry} set to {Convert.ToString((int)mode & 0xFFF, 8)}");
        }
    }

    private static void TryDeleteEmpty(string path)
    {
        try { Directory.Delete(path); } catch (IOException) { }
    }

    /// <summary>The group name that owns <paramref name="path"/> on Linux and macOS; null when it cannot be told.</summary>
    public static string? GroupOf(string path)
    {
        if (OperatingSystem.IsWindows()) return null;
        var (code, output) = OperatingSystem.IsMacOS() ? Run("stat", "-f", "%Sg", path) : Run("stat", "-c", "%G", path);
        return code == 0 && output.Length > 0 ? output : null;
    }

    /// <summary>True or false when the lookup tool answered; null when it is not available (the later chgrp then decides).</summary>
    private static bool? GroupExists(string group, DataDirectoryPlatform platform)
    {
        var (code, _) = platform == DataDirectoryPlatform.MacOS
            ? Run("dscl", ".", "-read", $"/Groups/{group}", "PrimaryGroupID")
            : Run("getent", "group", group);
        return code switch { 0 => true, -1 => null, _ => false };
    }

    /// <summary>Runs a tool and returns its exit code (-1 when it cannot be started) and trimmed stdout, or stderr when it failed.</summary>
    private static (int Code, string Output) Run(string file, params string[] args)
    {
        var start = new ProcessStartInfo(file)
        {
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
        };
        foreach (var arg in args) start.ArgumentList.Add(arg);
        try
        {
            using var process = Process.Start(start)!;
            var stdout = process.StandardOutput.ReadToEndAsync();
            var stderr = process.StandardError.ReadToEndAsync();
            process.WaitForExit();
            return (process.ExitCode, (process.ExitCode == 0 ? stdout.Result : stderr.Result).Trim());
        }
        catch (System.ComponentModel.Win32Exception)
        {
            return (-1, "");
        }
    }

    private static DataDirectoryInitResult InitializeWindows(string path, List<string> actions)
    {
        if (!OperatingSystem.IsWindows()) throw new PlatformNotSupportedException();
        ApplyWindowsAcl(path, actions);
        return new DataDirectoryInitResult(true, actions, null);
    }

    [SupportedOSPlatform("windows")]
    private static void ApplyWindowsAcl(string path, List<string> actions)
    {
        if (!Directory.Exists(path))
        {
            Directory.CreateDirectory(path);
            actions.Add($"Created {path}");
        }

        var users = new SecurityIdentifier(WellKnownSidType.BuiltinUsersSid, null);
        var info = new DirectoryInfo(path);
        var security = info.GetAccessControl();
        // AddAccessRule merges with an existing rule for the same identity, so running again changes nothing.
        security.AddAccessRule(new FileSystemAccessRule(users, FileSystemRights.Modify | FileSystemRights.Synchronize,
            InheritanceFlags.ContainerInherit | InheritanceFlags.ObjectInherit, PropagationFlags.None, AccessControlType.Allow));
        info.SetAccessControl(security);
        actions.Add(@"Granted BUILTIN\Users inheritable Modify on " + path);
    }
}

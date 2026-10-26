using System.Diagnostics;
using System.Text.RegularExpressions;

namespace MiresSftpUploader.Core;

/// <summary>
/// The real <see cref="IMachineIdentity"/>: the OS machine identifier (Windows <c>MachineGuid</c>, macOS <c>IOPlatformUUID</c>,
/// Linux <c>/etc/machine-id</c>) and the current account. Null when the machine has no readable identifier.
/// </summary>
public sealed partial class OsMachineIdentity : IMachineIdentity
{
    public string? MachineId { get; } = Read();

    public string Account { get; } = Environment.UserName;

    private static string? Read()
    {
        try
        {
            if (OperatingSystem.IsWindows()) return ReadWindows();
            if (OperatingSystem.IsMacOS()) return ReadMacOs();
            return ReadLinux();
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException or System.ComponentModel.Win32Exception or InvalidOperationException)
        {
            return null;
        }
    }

    [System.Runtime.Versioning.SupportedOSPlatform("windows")]
    private static string? ReadWindows()
    {
        using var key = Microsoft.Win32.RegistryKey.OpenBaseKey(Microsoft.Win32.RegistryHive.LocalMachine, Microsoft.Win32.RegistryView.Registry64)
            .OpenSubKey(@"SOFTWARE\Microsoft\Cryptography");
        return key?.GetValue("MachineGuid") as string;
    }

    private static string? ReadMacOs()
    {
        using var process = Process.Start(new ProcessStartInfo("/usr/sbin/ioreg", "-rd1 -c IOPlatformExpertDevice")
        {
            RedirectStandardOutput = true,
            UseShellExecute = false,
        });
        if (process is null) return null;
        var output = process.StandardOutput.ReadToEnd();
        process.WaitForExit();
        var match = PlatformUuid().Match(output);
        return match.Success ? match.Groups[1].Value : null;
    }

    private static string? ReadLinux() =>
        new[] { "/etc/machine-id", "/var/lib/dbus/machine-id" }
            .Where(File.Exists)
            .Select(p => File.ReadAllText(p).Trim())
            .FirstOrDefault(id => id.Length > 0);

    [GeneratedRegex("\"IOPlatformUUID\"\\s*=\\s*\"([^\"]+)\"")]
    private static partial Regex PlatformUuid();
}

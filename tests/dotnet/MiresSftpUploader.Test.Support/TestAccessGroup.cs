using MiresSftpUploader.Core;

namespace MiresSftpUploader.Test.Support;

/// <summary>
/// A group that exists on every machine the tests run on: the group a freshly created directory gets. Tests pass it as
/// State:AccessGroup so the Data Directory setup does not depend on a <c>mires-uploader</c> group being present.
/// </summary>
public static class TestAccessGroup
{
    private static readonly Lazy<string?> Group = new(() =>
    {
        var probe = Directory.CreateTempSubdirectory("mires-group-");
        try { return DataDirectory.GroupOf(probe.FullName); }
        finally { probe.Delete(); }
    });

    /// <summary>Null on Windows, where no group is used.</summary>
    public static string? Name => Group.Value;
}

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;

namespace MiresSftpUploader.SettingsTui;

/// <summary>One entry of a directory listing.</summary>
public readonly record struct PathEntry(string Name, bool IsDirectory);

/// <summary>Lists a directory for completion; a seam so Windows-style paths can be tested on any machine.</summary>
public interface IDirectoryListing
{
    /// <summary>The entries of <paramref name="directory"/>; empty when it does not exist or cannot be read. An empty string means the current directory.</summary>
    IEnumerable<PathEntry> Entries(string directory);
}

/// <summary>The local file system. Never touches a remote location.</summary>
public sealed class LocalListing : IDirectoryListing
{
    public static readonly LocalListing Instance = new();

    public IEnumerable<PathEntry> Entries(string directory)
    {
        try
        {
            var dir = new DirectoryInfo(directory.Length == 0 ? "." : directory);
            if (!dir.Exists) return [];
            return dir.EnumerateFileSystemInfos().Select(e => new PathEntry(e.Name, e.Attributes.HasFlag(FileAttributes.Directory))).ToList();
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException or ArgumentException or NotSupportedException)
        {
            return [];
        }
    }
}

/// <summary>
/// Tab completion for path fields, as pure functions. A unique match completes (a directory gets a trailing separator); several complete the
/// common prefix and are listed, directories first; <c>~</c> and <c>~/</c> expand to the home directory on Unix; a directory typed in full gets its separator, a file typed in full is complete as it is (Tab moves on); hidden entries (a leading dot)
/// show only when the typed name starts with a dot. Windows-style paths use either separator and the one the user typed is kept; matching ignores case.
/// </summary>
public static class PathCompletion
{
    /// <param name="Text">The field text after completing.</param>
    /// <param name="Candidates">Names to show when more than one entry matches (directories end with a separator).</param>
    public sealed record Result(string Text, IReadOnlyList<string> Candidates)
    {
        /// <summary>True when Tab did something: the text changed or candidates were listed. False means there is nothing to complete and Tab should navigate.</summary>
        public bool HasEffect(string input) => Text != input || Candidates.Count > 0;
    }

    public static Result Complete(string input, IDirectoryListing listing, string? home, bool windows)
    {
        var none = new Result(input, []);
        if (input.Length == 0) return none;

        var typed = input;
        if (!windows && !string.IsNullOrEmpty(home) && (input == "~" || input.StartsWith("~/", StringComparison.Ordinal)))
            typed = Path.TrimEndingDirectorySeparator(home) + "/" + input[(input == "~" ? 1 : 2)..];

        var sepChars = windows ? new[] { '\\', '/' } : ['/'];
        var cut = typed.LastIndexOfAny(sepChars);
        var dir = typed[..(cut + 1)];
        var prefix = typed[(cut + 1)..];
        var separator = cut >= 0 ? typed[cut] : windows ? '\\' : '/';
        if (input == "~" && typed != input) { dir = typed; prefix = ""; separator = '/'; } // "~" lists home

        var comparison = windows ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal;
        var matches = listing.Entries(dir)
            .Where(e => e.Name.StartsWith(prefix, comparison) && (!e.Name.StartsWith('.') || prefix.StartsWith('.')))
            .OrderBy(e => e.IsDirectory ? 0 : 1)
            .ThenBy(e => e.Name, windows ? StringComparer.OrdinalIgnoreCase : StringComparer.Ordinal)
            .ToList();
        if (matches.Count == 0) return typed == input ? none : new Result(typed, []);

        if (matches.Count == 1)
        {
            var only = matches[0];
            if (only.Name.Length == prefix.Length && !only.IsDirectory) return typed == input ? none : new Result(typed, []); // a file typed in full: nothing to complete, Tab moves on
            return new Result(dir + only.Name + (only.IsDirectory ? separator.ToString() : ""), []);
        }

        var common = matches[0].Name;
        foreach (var m in matches)
        {
            var n = 0;
            while (n < common.Length && n < m.Name.Length && string.Equals(common[n].ToString(), m.Name[n].ToString(), comparison)) n++;
            common = common[..n];
        }

        var names = matches.Select(m => m.IsDirectory ? m.Name + separator : m.Name).ToList();
        return new Result(dir + (common.Length > prefix.Length ? common : prefix), names);
    }

    /// <summary>Completion against the local file system of this machine, with the real home directory.</summary>
    public static Result CompleteLocal(string input) =>
        Complete(input, LocalListing.Instance, Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), OperatingSystem.IsWindows());
}

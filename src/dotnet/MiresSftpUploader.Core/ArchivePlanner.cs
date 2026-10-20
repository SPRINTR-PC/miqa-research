using System.Globalization;
using System.Text.RegularExpressions;

namespace MiresSftpUploader.Core;

/// <summary>An Archive the rules call for: its place in the Source, its members and what, if anything, stops it.</summary>
internal sealed record PlannedArchive(
    string RuleName, string RelativePath, IReadOnlyList<PlannedMember> Members, bool DeferredTooRecent, bool NameCollision)
{
    public long TotalSize => Members.Sum(m => m.Item.File.Size);
}

internal sealed record PlannedMember(Engine.FileWork Item, string EntryName);

/// <summary>Files that stay individual files, each flagged when Too Recent, plus the planned Archives.</summary>
internal sealed record ArchivePlan(
    IReadOnlyList<(Engine.FileWork Item, bool TooRecent)> Individual, IReadOnlyList<PlannedArchive> Archives);

/// <summary>
/// Applies the Archive Rules to the files of one Source that survived the Ignore Rules.
/// The first rule whose pattern matches a file wins; a group smaller than the rule's MinFiles stays individual files.
/// </summary>
internal static class ArchivePlanner
{
    public static ArchivePlan Plan(
        IReadOnlyList<ArchiveRuleConfig> rules,
        IReadOnlyList<(Engine.FileWork Item, bool TooRecent)> candidates,
        string sourceName,
        DateTimeOffset runStartedAt)
    {
        if (rules.Count == 0) return new ArchivePlan(candidates, []);

        var compiled = rules.Select(r => (Rule: r, Regex: new Regex(r.Pattern!,
            RegexOptions.IgnoreCase | RegexOptions.CultureInvariant, IgnoreRules.PatternTimeout))).ToList();

        var groups = new Dictionary<(int Rule, string Directory), List<(Engine.FileWork Item, bool TooRecent)>>();
        var individual = new List<(Engine.FileWork Item, bool TooRecent)>();
        foreach (var candidate in candidates)
        {
            var path = candidate.Item.File.RelativePath;
            var index = compiled.FindIndex(c => Matches(c.Regex, path));
            if (index < 0) { individual.Add(candidate); continue; }
            var directory = compiled[index].Rule.Grouping == ArchiveGrouping.PerDirectory ? DirectoryOf(path) : "";
            if (!groups.TryGetValue((index, directory), out var members)) groups[(index, directory)] = members = [];
            members.Add(candidate);
        }

        var archives = new List<PlannedArchive>();
        foreach (var ((index, directory), members) in groups.OrderBy(g => g.Key.Rule).ThenBy(g => g.Key.Directory, StringComparer.Ordinal))
        {
            var rule = compiled[index].Rule;
            if (members.Count < rule.MinFiles) { individual.AddRange(members); continue; }

            var name = ExpandName(rule, directory, sourceName, runStartedAt);
            var relativePath = directory.Length == 0 ? name : directory + "/" + name;
            var specs = members
                .Select(m => new PlannedMember(m.Item, EntryName(m.Item.File.RelativePath, directory)))
                .OrderBy(m => m.EntryName, StringComparer.Ordinal)
                .ToList();
            archives.Add(new PlannedArchive(rule.Name!, relativePath, specs, members.Any(m => m.TooRecent), NameCollision: false));
        }

        // An Archive may not take the place of an ordinary file, nor of another Archive.
        var taken = new HashSet<string>(individual.Select(i => i.Item.File.RelativePath), StringComparer.Ordinal);
        var claimed = archives.GroupBy(a => a.RelativePath, StringComparer.Ordinal).ToDictionary(g => g.Key, g => g.Count());
        for (var i = 0; i < archives.Count; i++)
            if (taken.Contains(archives[i].RelativePath) || claimed[archives[i].RelativePath] > 1)
                archives[i] = archives[i] with { NameCollision = true };

        return new ArchivePlan(individual, archives);
    }

    private static bool Matches(Regex regex, string path)
    {
        try { return regex.IsMatch(path); }
        catch (RegexMatchTimeoutException) { return false; }
    }

    private static string DirectoryOf(string path)
    {
        var slash = path.LastIndexOf('/');
        return slash < 0 ? "" : path[..slash];
    }

    private static string EntryName(string path, string directory) =>
        directory.Length == 0 ? path : path[(directory.Length + 1)..];

    private static string ExpandName(ArchiveRuleConfig rule, string directory, string sourceName, DateTimeOffset runStartedAt)
    {
        var dir = directory.Length == 0 ? sourceName : directory[(directory.LastIndexOf('/') + 1)..];
        return rule.ArchiveName
            .Replace("{rule}", rule.Name, StringComparison.Ordinal)
            .Replace("{dir}", dir, StringComparison.Ordinal)
            .Replace("{date}", runStartedAt.UtcDateTime.ToString("yyyyMMdd", CultureInfo.InvariantCulture), StringComparison.Ordinal);
    }
}

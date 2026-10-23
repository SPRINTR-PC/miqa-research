using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using MiresSftpUploader.Core;
using ReactiveUI;

namespace MiresSftpUploader.ViewModels;

/// <summary>One Archive Rule being edited: which files to pack, how they are grouped and what the Archive is called.</summary>
public sealed class ArchiveRuleEditorViewModel : ViewModelBase
{
    public static IReadOnlyList<string> GroupingNames { get; } = Enum.GetNames<ArchiveGrouping>();

    private static readonly ArchiveRuleConfig Defaults = new();

    private string _name;
    private string _pattern;
    private string _grouping;
    private string _archiveName;
    private string _minFiles;

    internal ArchiveRuleEditorViewModel(IReadOnlyDictionary<string, string> entry)
    {
        string Get(string key, string fallback) => entry.TryGetValue(key, out var v) ? v : fallback;
        _name = Get("Name", "");
        _pattern = Get("Pattern", "");
        _grouping = Enum.TryParse<ArchiveGrouping>(Get("Grouping", ""), true, out var g) ? g.ToString() : Defaults.Grouping.ToString();
        _archiveName = Get("ArchiveName", Defaults.ArchiveName);
        _minFiles = Get("MinFiles", Defaults.MinFiles.ToString());
    }

    internal static ArchiveRuleEditorViewModel Blank() => new(new Dictionary<string, string>());

    internal event Action? Edited;

    public string Name { get => _name; set => Set(ref _name, value); }
    public string Pattern { get => _pattern; set => Set(ref _pattern, value); }
    public string Grouping { get => _grouping; set => Set(ref _grouping, value); }
    public string ArchiveName { get => _archiveName; set => Set(ref _archiveName, value); }
    /// <summary>Kept as text so a half-typed value shows an error instead of being lost.</summary>
    public string MinFiles { get => _minFiles; set => Set(ref _minFiles, value); }

    /// <summary>The flat keys relative to the rule, as the configuration stores them.</summary>
    internal Dictionary<string, string> ToEntry() => new()
    {
        ["Name"] = Name.Trim(),
        ["Pattern"] = Pattern,
        ["Grouping"] = Grouping,
        ["ArchiveName"] = ArchiveName.Trim().Length == 0 ? Defaults.ArchiveName : ArchiveName.Trim(),
        ["MinFiles"] = MinFiles.Trim().Length == 0 ? Defaults.MinFiles.ToString() : MinFiles.Trim(),
    };

    private void Set<T>(ref T field, T value, [CallerMemberName] string? property = null)
    {
        if (EqualityComparer<T>.Default.Equals(field, value)) return;
        this.RaiseAndSetIfChanged(ref field, value, property);
        Edited?.Invoke();
    }
}

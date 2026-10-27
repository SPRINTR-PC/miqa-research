using System.Collections.Generic;
using System.Linq;
using MiresSftpUploader.ViewModels;

namespace MiresSftpUploader.SettingsTui;

/// <summary>Every problem (<c>✗</c>, disables Save) and warning (<c>!</c>) of the Settings page, for the F4 list and the status line.</summary>
public static class IssueList
{
    public static IReadOnlyList<string> Errors(SettingsPageViewModel vm)
    {
        var lines = new List<string>();
        lines.AddRange(vm.Fields.Where(f => f.HasError).Select(f => $"✗ {f.Label}: {f.Error}"));
        lines.AddRange(vm.Sources.Where(s => s.HasError).Select(s => $"✗ Source {s.Name}: {s.Error}"));
        if (vm.ArchiveRules.HasError) lines.Add("✗ Archive Rules: " + vm.ArchiveRules.Error);
        lines.AddRange(vm.OtherErrors.Select(e => "✗ " + e));
        return lines;
    }

    public static IReadOnlyList<string> All(SettingsPageViewModel vm)
    {
        var lines = Errors(vm).Concat(vm.Warnings.Select(w => "! " + w)).ToList();
        if (lines.Count == 0) lines.Add("No problems.");
        return lines;
    }
}

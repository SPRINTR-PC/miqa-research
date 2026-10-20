using System.Collections.Generic;

namespace MiresSftpUploader.ViewModels;

/// <summary>A titled group of settings on the Settings page.</summary>
public sealed record SettingsGroupViewModel(string Title, IReadOnlyList<SettingFieldViewModel> Fields);

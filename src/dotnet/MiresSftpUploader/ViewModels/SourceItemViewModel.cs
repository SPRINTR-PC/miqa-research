using MiresSftpUploader.Core;
using ReactiveUI;

namespace MiresSftpUploader.ViewModels;

/// <summary>A configured Source in the sidebar, with the checkbox that includes it in the next Run.</summary>
public sealed class SourceItemViewModel(SourceConfig config) : ViewModelBase
{
    private bool _included = true;

    public string Name { get; } = config.Name ?? "";

    /// <summary>One line: the type and where the files are.</summary>
    public string Summary { get; } = config.Type == SourceType.S3
        ? $"S3 · {config.Bucket}/{config.Prefix}"
        : $"Directory · {config.Path}";

    public bool Included
    {
        get => _included;
        set => this.RaiseAndSetIfChanged(ref _included, value);
    }
}

using Avalonia.Media;
using MiresSftpUploader.Core;
using MiresSftpUploader.ViewModels;

namespace MiresSftpUploader.Views;

/// <summary>The icons of the four Upload tiles: the same paths as the file list (<see cref="FileRowViewModel.IconFor"/>), as Geometry, which is what PathIcon.Data takes.</summary>
public static class OutcomeIcons
{
    public static Geometry SucceededIcon { get; } = Geometry.Parse(FileRowViewModel.IconFor(FileOutcome.Succeeded));
    public static Geometry FailedIcon { get; } = Geometry.Parse(FileRowViewModel.IconFor(FileOutcome.Failed));
    public static Geometry SkippedIcon { get; } = Geometry.Parse(FileRowViewModel.IconFor(FileOutcome.Skipped));
    public static Geometry PendingIcon { get; } = Geometry.Parse(FileRowViewModel.IconFor(FileOutcome.Pending));
}

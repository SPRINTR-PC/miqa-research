namespace MiresSftpUploader.Core;

public abstract record RunEvent;

public sealed record RunStarted(Guid RunId, DateTimeOffset StartedAt) : RunEvent;

public sealed record FileOutcomeChanged(string Source, string RelativePath, FileOutcome Outcome, string? Reason) : RunEvent;

/// <summary>The Data Directory access check, reported at each Run start (also when it failed).</summary>
public sealed record DataDirectoryChecked(DataDirectoryAccess Access) : RunEvent;

public sealed record RunWarning(string Message) : RunEvent;

public sealed record RunFinished(RunResult Result) : RunEvent;

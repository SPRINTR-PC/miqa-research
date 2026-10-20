namespace MiresSftpUploader.Core;

public abstract record RunEvent;

public sealed record RunStarted(Guid RunId, DateTimeOffset StartedAt) : RunEvent;

public sealed record FileOutcomeChanged(string Source, string RelativePath, FileOutcome Outcome, string? Reason) : RunEvent;

public sealed record RunWarning(string Message) : RunEvent;

public sealed record RunFinished(RunResult Result) : RunEvent;

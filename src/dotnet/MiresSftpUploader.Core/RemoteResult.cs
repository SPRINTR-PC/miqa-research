namespace MiresSftpUploader.Core;

public enum RemoteResultKind { Ok, Denied, Failed }

/// <summary>Outcome of one remote operation: Ok, Denied or Failed(reason). Remote adapters return these instead of throwing.</summary>
public record RemoteResult(RemoteResultKind Kind, string? Reason = null)
{
    public static RemoteResult Ok { get; } = new(RemoteResultKind.Ok);
    public static RemoteResult Denied(string reason) => new(RemoteResultKind.Denied, reason);
    public static RemoteResult Failed(string reason) => new(RemoteResultKind.Failed, reason);

    public bool IsOk => Kind == RemoteResultKind.Ok;
}

/// <summary>A result that carries a value when Ok.</summary>
public sealed record RemoteResult<T>(RemoteResultKind Kind, T? Value = default, string? Reason = null)
{
    public static RemoteResult<T> Ok(T value) => new(RemoteResultKind.Ok, value);
    public static RemoteResult<T> Denied(string reason) => new(RemoteResultKind.Denied, default, reason);
    public static RemoteResult<T> Failed(string reason) => new(RemoteResultKind.Failed, default, reason);

    public bool IsOk => Kind == RemoteResultKind.Ok;

    public RemoteResult WithoutValue() => new(Kind, Reason);
}

/// <summary>Size of an object on the server, as reported by <see cref="IRemoteSession.StatAsync"/>.</summary>
public sealed record RemoteFileInfo(long Size);

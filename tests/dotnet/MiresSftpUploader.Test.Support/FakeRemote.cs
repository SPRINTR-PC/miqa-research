using System.Collections.Concurrent;
using MiresSftpUploader.Core;

namespace MiresSftpUploader.Test.Support;

public enum RemoteOperation { Connect, EnsureDirectory, Upload, Rename, Delete, Stat }

/// <summary>
/// In-memory <see cref="IRemote"/> with fault injection. Paths are forward-slash, rooted at "/".
/// </summary>
public sealed class FakeRemote : IRemote
{
    private readonly object _gate = new();
    private readonly Dictionary<string, byte[]> _files = new();
    private readonly HashSet<string> _directories = new() { "/" };
    private readonly List<Fault> _faults = new();

    public int ConnectCount { get; private set; }

    /// <summary>Snapshot of every object on the server, keyed by full path.</summary>
    public IReadOnlyDictionary<string, byte[]> Files
    {
        get { lock (_gate) return new Dictionary<string, byte[]>(_files); }
    }

    public IReadOnlyCollection<string> Directories
    {
        get { lock (_gate) return _directories.ToArray(); }
    }

    public string ReadText(string path) => System.Text.Encoding.UTF8.GetString(Files[path]);

    /// <summary>
    /// Makes the next <paramref name="times"/> matching operations return <paramref name="result"/>.
    /// A null <paramref name="pathContains"/> matches any path.
    /// </summary>
    public void Inject(RemoteOperation operation, RemoteResult result, int times = 1, string? pathContains = null)
    {
        lock (_gate) _faults.Add(new Fault(operation, pathContains, times, result));
    }

    public Task<RemoteResult<IRemoteSession>> ConnectAsync(CancellationToken cancellationToken)
    {
        lock (_gate) ConnectCount++;
        var fault = TakeFault(RemoteOperation.Connect, "");
        return Task.FromResult(fault is null
            ? RemoteResult<IRemoteSession>.Ok(new Session(this))
            : new RemoteResult<IRemoteSession>(fault.Kind, default, fault.Reason));
    }

    internal RemoteResult? TakeFault(RemoteOperation operation, string path)
    {
        lock (_gate)
        {
            foreach (var f in _faults)
            {
                if (f.Operation != operation || f.Remaining <= 0) continue;
                if (f.PathContains is not null && !path.Contains(f.PathContains, StringComparison.Ordinal)) continue;
                f.Remaining--;
                return f.Result;
            }
        }
        return null;
    }

    private sealed class Fault(RemoteOperation operation, string? pathContains, int remaining, RemoteResult result)
    {
        public RemoteOperation Operation { get; } = operation;
        public string? PathContains { get; } = pathContains;
        public int Remaining { get; set; } = remaining;
        public RemoteResult Result { get; } = result;
    }

    private sealed class Session(FakeRemote remote) : IRemoteSession
    {
        public Task<RemoteResult> EnsureDirectoryAsync(string path, CancellationToken ct)
        {
            if (remote.TakeFault(RemoteOperation.EnsureDirectory, path) is { } fault) return Task.FromResult(fault);
            lock (remote._gate)
            {
                var current = "";
                foreach (var part in path.Split('/', StringSplitOptions.RemoveEmptyEntries))
                {
                    current += "/" + part;
                    remote._directories.Add(current);
                }
            }
            return Task.FromResult(RemoteResult.Ok);
        }

        public async Task<RemoteResult> UploadAsync(Stream content, string path, CancellationToken ct)
        {
            if (remote.TakeFault(RemoteOperation.Upload, path) is { } fault) return fault;
            var buffer = new MemoryStream();
            await content.CopyToAsync(buffer, ct);
            lock (remote._gate)
            {
                var parent = path[..Math.Max(path.LastIndexOf('/'), 0)];
                if (parent.Length > 0 && !remote._directories.Contains(parent))
                    return RemoteResult.Failed($"directory does not exist: {parent}");
                remote._files[path] = buffer.ToArray();
            }
            return RemoteResult.Ok;
        }

        public Task<RemoteResult> RenameAsync(string from, string to, bool overwrite, CancellationToken ct)
        {
            if (remote.TakeFault(RemoteOperation.Rename, from) is { } fault) return Task.FromResult(fault);
            lock (remote._gate)
            {
                if (!remote._files.TryGetValue(from, out var data))
                    return Task.FromResult(RemoteResult.Failed($"not found: {from}"));
                if (!overwrite && remote._files.ContainsKey(to))
                    return Task.FromResult(RemoteResult.Failed($"already exists: {to}"));
                remote._files.Remove(from);
                remote._files[to] = data;
            }
            return Task.FromResult(RemoteResult.Ok);
        }

        public Task<RemoteResult> DeleteAsync(string path, CancellationToken ct)
        {
            if (remote.TakeFault(RemoteOperation.Delete, path) is { } fault) return Task.FromResult(fault);
            lock (remote._gate)
                return Task.FromResult(remote._files.Remove(path) ? RemoteResult.Ok : RemoteResult.Failed($"not found: {path}"));
        }

        public Task<RemoteResult<RemoteFileInfo>> StatAsync(string path, CancellationToken ct)
        {
            if (remote.TakeFault(RemoteOperation.Stat, path) is { } fault)
                return Task.FromResult(new RemoteResult<RemoteFileInfo>(fault.Kind, default, fault.Reason));
            lock (remote._gate)
                return Task.FromResult(remote._files.TryGetValue(path, out var data)
                    ? RemoteResult<RemoteFileInfo>.Ok(new RemoteFileInfo(data.Length))
                    : RemoteResult<RemoteFileInfo>.Failed($"not found: {path}"));
        }

        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }
}

using System.Collections.Concurrent;
using MiresSftpUploader.Core;

namespace MiresSftpUploader.Test.Support;

public enum RemoteOperation { Connect, EnsureDirectory, Upload, Rename, Delete, Stat, Download, RunCommand }

/// <summary>
/// In-memory <see cref="IRemote"/> with fault injection. Paths are forward-slash, rooted at "/".
/// </summary>
public sealed class FakeRemote : IRemote
{
    private readonly object _gate = new();
    private readonly Dictionary<string, byte[]> _files = new();
    private readonly HashSet<string> _directories = new() { "/" };
    private readonly List<Fault> _faults = new();

    private readonly List<string> _commands = new();
    private readonly List<Corruption> _corruptions = new();

    public int ConnectCount { get; private set; }

    /// <summary>False models an SFTP-only account: <c>RunCommandAsync</c> fails.</summary>
    public bool CommandChannel { get; set; } = true;

    /// <summary>Every command <c>RunCommandAsync</c> received, in order.</summary>
    public IReadOnlyList<string> Commands
    {
        get { lock (_gate) return _commands.ToArray(); }
    }

    /// <summary>Puts an object on the server without going through a session (and creates its directory).</summary>
    public void PutFile(string path, byte[] content)
    {
        lock (_gate)
        {
            var current = "";
            foreach (var part in path.Split('/', StringSplitOptions.RemoveEmptyEntries).SkipLast(1))
                _directories.Add(current += "/" + part);
            _files[path] = content;
        }
    }

    /// <summary>
    /// Makes the next <paramref name="times"/> uploads to a matching path store damaged content: the last byte changed, or
    /// with <paramref name="truncate"/> the last byte missing. The upload itself reports success.
    /// </summary>
    public void CorruptNextUpload(string pathContains, bool truncate = false, int times = 1)
    {
        lock (_gate) _corruptions.Add(new Corruption(pathContains, truncate, times));
    }

    private sealed class Corruption(string pathContains, bool truncate, int remaining)
    {
        public string PathContains { get; } = pathContains;
        public bool Truncate { get; } = truncate;
        public int Remaining { get; set; } = remaining;
    }

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
                var stored = buffer.ToArray();
                var corruption = remote._corruptions.FirstOrDefault(c => c.Remaining > 0 && path.Contains(c.PathContains, StringComparison.Ordinal));
                if (corruption is not null && stored.Length > 0)
                {
                    corruption.Remaining--;
                    if (corruption.Truncate) stored = stored[..^1];
                    else stored[^1] ^= 0xFF;
                }
                remote._files[path] = stored;
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

        public async Task<RemoteResult> DownloadAsync(string path, Stream destination, CancellationToken ct)
        {
            if (remote.TakeFault(RemoteOperation.Download, path) is { } fault) return fault;
            byte[]? data;
            lock (remote._gate) remote._files.TryGetValue(path, out data);
            if (data is null) return RemoteResult.Failed($"not found: {path}");
            await destination.WriteAsync(data, ct);
            return RemoteResult.Ok;
        }

        private const string Quote = "'";
        private const string EscapedQuote = "'\\''";

        /// <summary>Understands exactly one command: <c>sha256sum -- '&lt;path&gt;'</c>, the default template with its quoted path.</summary>
        public Task<RemoteResult<string>> RunCommandAsync(string command, CancellationToken ct)
        {
            lock (remote._gate) remote._commands.Add(command);
            if (remote.TakeFault(RemoteOperation.RunCommand, command) is { } fault)
                return Task.FromResult(new RemoteResult<string>(fault.Kind, default, fault.Reason));
            if (!remote.CommandChannel)
                return Task.FromResult(RemoteResult<string>.Failed("the server offers no command channel (SFTP only)"));

            const string prefix = "sha256sum -- '";
            if (!command.StartsWith(prefix, StringComparison.Ordinal) || !command.EndsWith(Quote, StringComparison.Ordinal))
                return Task.FromResult(RemoteResult<string>.Failed("sh: command not found: " + command));
            var path = command[prefix.Length..^1].Replace(EscapedQuote, Quote, StringComparison.Ordinal);
            byte[]? data;
            if (path == "/dev/null") data = [];
            else lock (remote._gate) remote._files.TryGetValue(path, out data);
            if (data is null)
                return Task.FromResult(RemoteResult<string>.Failed($"sha256sum: {path}: No such file or directory"));
            return Task.FromResult(RemoteResult<string>.Ok(Convert.ToHexStringLower(System.Security.Cryptography.SHA256.HashData(data)) + "  " + path + "\n"));
        }

        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }
}

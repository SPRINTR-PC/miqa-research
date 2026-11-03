using System.Security.Cryptography;

namespace MiresSftpUploader.Core;

public sealed partial class Engine
{
    internal const string VerificationFailedReason = "VerificationFailed";

    /// <summary>The result of checking one object on the server. <see cref="Missing"/> tells "not there" from "there but wrong".</summary>
    private sealed record VerifyResult(bool Ok, bool Missing, string? Detail)
    {
        public static VerifyResult Passed { get; } = new(true, false, null);
        public static VerifyResult NotThere(string path) => new(false, true, $"the remote copy is missing ({path})");
        public static VerifyResult Differs(string detail) => new(false, false, "the remote copy differs: " + detail);
        public static VerifyResult Unreadable(string detail) => new(false, false, detail);
    }

    /// <summary>
    /// Checks that the object at <paramref name="path"/> has the size and SHA-256 the Run holds for it, at the given level.
    /// Bounded by the configured timeout, which counts as a failed check.
    /// </summary>
    private async Task<VerifyResult> VerifyAsync(IRemoteSession session, VerificationLevel level, string path, long size, string sha256, CancellationToken ct)
    {
        using var timeout = new CancellationTokenSource(_settings.Verification.Timeout, _time);
        using var linked = CancellationTokenSource.CreateLinkedTokenSource(ct, timeout.Token);
        try
        {
            return level switch
            {
                VerificationLevel.Size => await VerifySizeAsync(session, path, size, linked.Token),
                VerificationLevel.Hash => await VerifyHashAsync(session, path, sha256, linked.Token),
                VerificationLevel.ReadBack => await VerifyReadBackAsync(session, path, size, sha256, linked.Token),
                _ => VerifyResult.Passed,
            };
        }
        catch (OperationCanceledException) when (timeout.IsCancellationRequested && !ct.IsCancellationRequested)
        {
            return VerifyResult.Unreadable($"timed out after {_settings.Verification.Timeout.TotalSeconds:0} s");
        }
    }

    private static async Task<VerifyResult> VerifySizeAsync(IRemoteSession session, string path, long size, CancellationToken ct)
    {
        var stat = await session.StatAsync(path, ct);
        if (!stat.IsOk)
            return IsNotFound(stat.Reason) ? VerifyResult.NotThere(path) : VerifyResult.Unreadable($"cannot stat {path}: {stat.Reason}");
        return stat.Value!.Size == size ? VerifyResult.Passed : VerifyResult.Differs($"size is {stat.Value.Size}, expected {size}");
    }

    private async Task<VerifyResult> VerifyHashAsync(IRemoteSession session, string path, string sha256, CancellationToken ct)
    {
        var run = await session.RunCommandAsync(VerifyCommand.Build(_settings.Verification.Command, path), ct);
        if (!run.IsOk)
            return run.Reason?.Contains("No such file", StringComparison.OrdinalIgnoreCase) == true
                ? VerifyResult.NotThere(path)
                : VerifyResult.Unreadable($"the verify command failed: {run.Reason}");
        var remote = VerifyCommand.ParseHash(run.Value!);
        if (remote is null) return VerifyResult.Unreadable("the verify command printed no SHA-256");
        return remote == sha256 ? VerifyResult.Passed : VerifyResult.Differs($"SHA-256 is {remote}, expected {sha256}");
    }

    private static async Task<VerifyResult> VerifyReadBackAsync(IRemoteSession session, string path, long size, string sha256, CancellationToken ct)
    {
        using var sink = new HashingSink();
        var download = await session.DownloadAsync(path, sink, ct);
        if (!download.IsOk)
            return IsNotFound(download.Reason) ? VerifyResult.NotThere(path) : VerifyResult.Unreadable($"cannot read {path} back: {download.Reason}");
        if (sink.Length != size) return VerifyResult.Differs($"read back {sink.Length} bytes, expected {size}");
        var remote = sink.Finish();
        return remote == sha256 ? VerifyResult.Passed : VerifyResult.Differs($"SHA-256 is {remote}, expected {sha256}");
    }

    private static bool IsNotFound(string? reason) => reason?.Contains("not found", StringComparison.OrdinalIgnoreCase) == true;

    /// <summary>
    /// Start of a Run: every Verification level that is configured must work on this server. An unavailable level ends the Run
    /// with exit code 2 and the cause; it is never lowered silently. Returns null when all levels work.
    /// </summary>
    private async Task<(int ExitCode, string? Reason)?> ProbeVerificationAsync(DateTimeOffset runStartedAt, CancellationToken ct)
    {
        var settings = _settings.Verification;
        var wanted = new List<(string Setting, VerificationLevel Level)>();
        if (settings.AfterUpload != VerificationLevel.Off) wanted.Add(("Upload:VerifyAfterUpload", settings.AfterUpload));
        if (settings.Remote != VerificationLevel.Off) wanted.Add(("Upload:VerifyRemote", settings.Remote));
        if (wanted.Count == 0) return null;

        var connect = await _remote.ConnectAsync(ct);
        if (!connect.IsOk) return (ExitCodes.ConnectFailed, connect.Reason);
        await using var session = connect.Value!;
        foreach (var (setting, level) in wanted)
        {
            var problem = await ProbeAsync(session, level, runStartedAt, ct);
            if (problem is not null)
                return (ExitCodes.ConfigurationError, $"{setting} is {level}, which this server cannot do: {problem}");
        }
        return null;
    }

    private async Task<string?> ProbeAsync(IRemoteSession session, VerificationLevel level, DateTimeOffset runStartedAt, CancellationToken ct)
    {
        if (level == VerificationLevel.Hash)
        {
            // The hash of an empty file is known, and /dev/null is harmless to read.
            var run = await session.RunCommandAsync(VerifyCommand.Build(_settings.Verification.Command, "/dev/null"), ct);
            if (!run.IsOk) return $"the verify command did not run ({run.Reason}). The server needs a command channel and the command must exist there.";
            return VerifyCommand.ParseHash(run.Value!) == HashingSink.EmptyHash
                ? null
                : $"the verify command printed '{run.Value!.Trim()}' for an empty file instead of its SHA-256.";
        }

        // Size and ReadBack both need to look at objects, which a write-only account cannot.
        var root = Normalize(RemotePathTemplate.Expand(_settings.RemoteRoot, runStartedAt));
        var ensure = await session.EnsureDirectoryAsync(root, ct);
        if (!ensure.IsOk) return $"cannot prepare {root}: {ensure.Reason}";
        var stat = await session.StatAsync(root, ct);
        return stat.IsOk ? null : $"the account cannot read from the server ({stat.Reason}).";
    }

    /// <summary>A write-only stream that hashes what is written to it, for the ReadBack level.</summary>
    private sealed class HashingSink : Stream
    {
        public static readonly string EmptyHash = Convert.ToHexStringLower(SHA256.HashData([]));
        private readonly IncrementalHash _hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        private long _length;

        public string Finish() => Convert.ToHexStringLower(_hash.GetHashAndReset());

        public override void Write(ReadOnlySpan<byte> buffer)
        {
            _hash.AppendData(buffer);
            _length += buffer.Length;
        }

        public override void Write(byte[] buffer, int offset, int count) => Write(buffer.AsSpan(offset, count));
        public override ValueTask WriteAsync(ReadOnlyMemory<byte> buffer, CancellationToken cancellationToken = default)
        {
            Write(buffer.Span);
            return ValueTask.CompletedTask;
        }

        public override bool CanRead => false;
        public override bool CanSeek => false;
        public override bool CanWrite => true;
        public override long Length => _length;
        public override long Position { get => _length; set => throw new NotSupportedException(); }
        public override void Flush() { }
        public override int Read(byte[] buffer, int offset, int count) => throw new NotSupportedException();
        public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
        public override void SetLength(long value) => throw new NotSupportedException();

        protected override void Dispose(bool disposing)
        {
            if (disposing) _hash.Dispose();
            base.Dispose(disposing);
        }
    }
}

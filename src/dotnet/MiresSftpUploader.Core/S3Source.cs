using System.Net;
using System.Runtime.CompilerServices;
using Amazon.Runtime;
using Amazon.S3;
using Amazon.S3.Model;

namespace MiresSftpUploader.Core;

/// <summary>
/// A Source backed by an S3-compatible bucket prefix. A file's version is its size and ETag (the ETag is never a content
/// hash); LastModified, cut to whole seconds because that is all <c>HEAD</c> returns, only serves Scan min-age.
/// Reading streams the object, so Archive members and uploads hash in the same pass without a separate download.
/// </summary>
public sealed class S3Source : ISource, IDisposable
{
    private readonly IAmazonS3 _client;
    private readonly string _bucket;
    private readonly string _prefix;

    public S3Source(string name, string bucket, string? prefix, string? remotePath, IAmazonS3 client)
    {
        Name = name;
        RemotePath = remotePath;
        _bucket = bucket;
        _prefix = NormalisePrefix(prefix);
        _client = client;
    }

    public string Name { get; }
    public string? RemotePath { get; }

    /// <summary>
    /// The client settings for a third-party S3 server: its <c>ServiceURL</c>, path-style addressing when asked, and
    /// checksums calculated and validated only when the protocol requires it (the SDK default breaks several servers).
    /// </summary>
    internal static AmazonS3Config CreateClientConfig(SourceConfig source) => new()
    {
        ServiceURL = source.Endpoint,
        ForcePathStyle = source.ForcePathStyle,
        AuthenticationRegion = string.IsNullOrWhiteSpace(source.Region) ? "us-east-1" : source.Region,
        RequestChecksumCalculation = RequestChecksumCalculation.WHEN_REQUIRED,
        ResponseChecksumValidation = ResponseChecksumValidation.WHEN_REQUIRED,
    };

    /// <summary>Always explicit credentials from the Secrets: the AWS credential chain is never consulted.</summary>
    internal static S3Source Create(SourceConfig source, S3Credentials credentials) =>
        new(source.Name!, source.Bucket!, source.Prefix, source.RemotePath,
            new AmazonS3Client(new BasicAWSCredentials(credentials.AccessKey, credentials.SecretKey), CreateClientConfig(source)));

    public async IAsyncEnumerable<SourceFile> ListAsync([EnumeratorCancellation] CancellationToken cancellationToken)
    {
        string? token = null;
        do
        {
            var response = await Call(() => _client.ListObjectsV2Async(
                new ListObjectsV2Request { BucketName = _bucket, Prefix = _prefix, ContinuationToken = token }, cancellationToken));
            foreach (var entry in response.S3Objects ?? [])
            {
                var relative = entry.Key.Length > _prefix.Length ? entry.Key[_prefix.Length..] : "";
                if (relative.Length == 0 || relative.EndsWith('/')) continue; // folder markers are not files
                yield return new SourceFile(relative, entry.Size ?? 0, WholeSeconds(entry.LastModified), Unquote(entry.ETag));
            }
            token = response.IsTruncated == true ? response.NextContinuationToken : null;
        } while (token is not null);
    }

    public async Task<SourceFile?> StatAsync(string relativePath, CancellationToken cancellationToken)
    {
        try
        {
            var head = await _client.GetObjectMetadataAsync(
                new GetObjectMetadataRequest { BucketName = _bucket, Key = _prefix + relativePath }, cancellationToken);
            return new SourceFile(relativePath, head.ContentLength, WholeSeconds(head.LastModified), Unquote(head.ETag));
        }
        catch (AmazonS3Exception ex) when (ex.StatusCode == HttpStatusCode.NotFound)
        {
            return null;
        }
        catch (AmazonServiceException ex)
        {
            throw new IOException($"S3 {Name}/{relativePath}: {ex.Message}", ex);
        }
    }

    public async Task<Stream> OpenReadAsync(string relativePath, CancellationToken cancellationToken)
    {
        var response = await Call(() => _client.GetObjectAsync(
            new GetObjectRequest { BucketName = _bucket, Key = _prefix + relativePath }, cancellationToken));
        return new ResponseOwningStream(response);
    }

    /// <summary>The largest object a single server-side copy handles; bigger ones are not moved.</summary>
    internal const long MaxCopyBytes = 5L * 1024 * 1024 * 1024;

    /// <summary>S3 has no move: copy to the target bucket and prefix, check the size, delete the original. Never overwrites.</summary>
    public async Task<MoveResult> MoveAsync(string relativePath, MoveTargetConfig target, CancellationToken cancellationToken)
    {
        var sourceKey = _prefix + relativePath;
        var targetBucket = target.Bucket!;
        var targetKey = NormalisePrefix(target.Prefix) + relativePath;
        try
        {
            var original = await HeadAsync(_bucket, sourceKey, cancellationToken);
            if (original is null) return MoveResult.Failed("the object is no longer in the Source");
            if (await HeadAsync(targetBucket, targetKey, cancellationToken) is not null)
                return MoveResult.TargetExists($"{targetBucket}/{targetKey}");
            if (original.ContentLength > MaxCopyBytes)
                return MoveResult.Failed($"the object has {original.ContentLength} bytes, more than the {MaxCopyBytes} a single S3 copy handles");

            await _client.CopyObjectAsync(new CopyObjectRequest
            {
                SourceBucket = _bucket, SourceKey = sourceKey, DestinationBucket = targetBucket, DestinationKey = targetKey,
            }, cancellationToken);

            var copy = await HeadAsync(targetBucket, targetKey, cancellationToken);
            if (copy is null || copy.ContentLength != original.ContentLength)
            {
                if (copy is not null)
                    await _client.DeleteObjectAsync(new DeleteObjectRequest { BucketName = targetBucket, Key = targetKey }, cancellationToken);
                return MoveResult.Failed($"the copy has {copy?.ContentLength.ToString() ?? "no"} bytes, expected {original.ContentLength}");
            }

            await _client.DeleteObjectAsync(new DeleteObjectRequest { BucketName = _bucket, Key = sourceKey }, cancellationToken);
            return MoveResult.Moved();
        }
        catch (AmazonServiceException ex)
        {
            return MoveResult.Failed($"S3: {ex.Message}");
        }
    }

    private async Task<GetObjectMetadataResponse?> HeadAsync(string bucket, string key, CancellationToken cancellationToken)
    {
        try
        {
            return await _client.GetObjectMetadataAsync(new GetObjectMetadataRequest { BucketName = bucket, Key = key }, cancellationToken);
        }
        catch (AmazonS3Exception ex) when (ex.StatusCode == HttpStatusCode.NotFound)
        {
            return null;
        }
    }

    public void Dispose() => _client.Dispose();

    /// <summary>SDK failures surface as <see cref="IOException"/>, like any other unreadable file, so one bad object fails only itself.</summary>
    private static async Task<T> Call<T>(Func<Task<T>> call)
    {
        try { return await call(); }
        catch (AmazonServiceException ex) { throw new IOException($"S3: {ex.Message}", ex); }
    }

    private static string NormalisePrefix(string? prefix)
    {
        var trimmed = (prefix ?? "").Trim().TrimStart('/');
        return trimmed.Length == 0 || trimmed.EndsWith('/') ? trimmed : trimmed + "/";
    }

    private static string? Unquote(string? etag) => etag?.Trim('"');

    private static DateTimeOffset WholeSeconds(DateTime? utc)
    {
        var value = utc is { } d ? DateTime.SpecifyKind(d, DateTimeKind.Utc) : DateTime.UnixEpoch;
        return new DateTimeOffset(value.Ticks - value.Ticks % TimeSpan.TicksPerSecond, TimeSpan.Zero);
    }

    /// <summary>The forward-only response stream; disposing it ends the HTTP response.</summary>
    private sealed class ResponseOwningStream(GetObjectResponse response) : Stream
    {
        private readonly Stream _inner = response.ResponseStream;

        public override bool CanRead => true;
        public override bool CanSeek => false;
        public override bool CanWrite => false;
        public override long Length => response.ContentLength;
        public override long Position { get => throw new NotSupportedException(); set => throw new NotSupportedException(); }
        public override void Flush() { }
        public override int Read(byte[] buffer, int offset, int count) => _inner.Read(buffer, offset, count);
        public override int Read(Span<byte> buffer) => _inner.Read(buffer);
        public override Task<int> ReadAsync(byte[] buffer, int offset, int count, CancellationToken ct) => _inner.ReadAsync(buffer, offset, count, ct);
        public override ValueTask<int> ReadAsync(Memory<byte> buffer, CancellationToken ct = default) => _inner.ReadAsync(buffer, ct);
        public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
        public override void SetLength(long value) => throw new NotSupportedException();
        public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();

        protected override void Dispose(bool disposing)
        {
            if (disposing) response.Dispose();
            base.Dispose(disposing);
        }
    }
}

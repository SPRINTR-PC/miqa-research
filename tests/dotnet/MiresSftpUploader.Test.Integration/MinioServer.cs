using Amazon.Runtime;
using Amazon.S3;
using Amazon.S3.Model;
using DotNet.Testcontainers.Builders;
using DotNet.Testcontainers.Containers;
using MiresSftpUploader.Core;

namespace MiresSftpUploader.Test.Integration;

/// <summary>Where to reach the throwaway MinIO container.</summary>
public sealed record MinioServerInfo(string Endpoint, string AccessKey, string SecretKey)
{
    public S3Credentials Credentials => new(AccessKey, SecretKey);

    /// <summary>The configuration of an S3 Source named <paramref name="name"/> over <paramref name="bucket"/> and <paramref name="prefix"/>.</summary>
    public SourceConfig Source(string name, string bucket, string? prefix = null) => new()
    {
        Name = name,
        Type = SourceType.S3,
        Endpoint = Endpoint,
        Bucket = bucket,
        Prefix = prefix,
        ForcePathStyle = true,
    };

    /// <summary>A client for seeding and inspecting buckets independently of the adapter under test.</summary>
    public AmazonS3Client AdminClient() => new(new BasicAWSCredentials(AccessKey, SecretKey),
        new AmazonS3Config { ServiceURL = Endpoint, ForcePathStyle = true, AuthenticationRegion = "us-east-1",
            RequestChecksumCalculation = RequestChecksumCalculation.WHEN_REQUIRED, ResponseChecksumValidation = ResponseChecksumValidation.WHEN_REQUIRED });

    /// <summary>Creates a fresh bucket holding exactly <paramref name="objects"/> (key to content).</summary>
    public async Task<string> NewBucketAsync(IReadOnlyDictionary<string, byte[]> objects)
    {
        var bucket = "t" + Guid.NewGuid().ToString("N")[..16];
        using var client = AdminClient();
        await client.PutBucketAsync(bucket);
        foreach (var (key, data) in objects)
            await client.PutObjectAsync(new PutObjectRequest { BucketName = bucket, Key = key, InputStream = new MemoryStream(data), AutoCloseStream = true });
        return bucket;
    }
}

/// <summary>One MinIO server (pinned image) shared by every S3 container test. Tests that cannot reach Docker end Inconclusive.</summary>
public static class MinioServer
{
    // bitnamilegacy/minio:2025.7.23, pinned by digest (the minio/minio images are no longer published on Docker Hub).
    private const string Image = "bitnamilegacy/minio@sha256:8935e75fa5d11295c17171e4aa49efe390a1193cd7f12e4d21b92af9ffef09d7";
    private const string AccessKey = "mires-test";
    private const string SecretKey = "mires-test-secret";

    private static readonly Lazy<Task<MinioServerInfo>> Started = new(StartAsync);
    private static IContainer? _container;

    public static MinioServerInfo Get()
    {
        try
        {
            return Started.Value.GetAwaiter().GetResult();
        }
        catch (Exception ex) when (ex is DockerUnavailableException or ArgumentException or HttpRequestException or TimeoutException
            || ex.GetType().Name.Contains("Docker", StringComparison.OrdinalIgnoreCase))
        {
            Assert.Inconclusive("Docker is not reachable: " + ex.Message);
            throw;
        }
    }

    public static async Task StopAsync()
    {
        if (_container is not null) await _container.DisposeAsync();
    }

    private static async Task<MinioServerInfo> StartAsync()
    {
        var container = new ContainerBuilder(Image)
            .WithPortBinding(9000, assignRandomHostPort: true)
            .WithEnvironment("MINIO_ROOT_USER", AccessKey)
            .WithEnvironment("MINIO_ROOT_PASSWORD", SecretKey)
            .WithWaitStrategy(Wait.ForUnixContainer().UntilHttpRequestIsSucceeded(r => r.ForPort(9000).ForPath("/minio/health/live")))
            .Build();
        try
        {
            await container.StartAsync();
        }
        catch (Exception ex) when (ex is not DockerUnavailableException
            && (ex.GetType().Name.Contains("Docker", StringComparison.OrdinalIgnoreCase) || ex.Message.Contains("docker", StringComparison.OrdinalIgnoreCase)))
        {
            throw new DockerUnavailableException(ex.Message);
        }
        _container = container;
        return new MinioServerInfo($"http://{container.Hostname}:{container.GetMappedPublicPort(9000)}", AccessKey, SecretKey);
    }
}

using MiresSftpUploader.Core;
using MiresSftpUploader.Test.Support;

namespace MiresSftpUploader.Test.Integration;

[TestClass]
[TestCategory("Container")]
public sealed class S3SourceContractTests : SourceContract
{
    protected override ISource CreateSource(IReadOnlyDictionary<string, byte[]> files)
    {
        var server = MinioServer.Get();
        var prefixed = files.ToDictionary(f => "contract/" + f.Key, f => f.Value);
        var bucket = server.NewBucketAsync(prefixed).GetAwaiter().GetResult();
        _bucket = bucket;
        return S3Source.Create(server.Source("contract", bucket, "contract"), server.Credentials);
    }

    private string _bucket = "";

    // The target lives in the Source's own bucket under a different prefix: same endpoint and credentials.
    protected override MoveTargetConfig CreateMoveTarget() =>
        new() { Action = MoveAction.Move, Bucket = _bucket, Prefix = "moved-" + Guid.NewGuid().ToString("N") };

    protected override byte[]? ReadMoveTarget(MoveTargetConfig target, string relativePath)
    {
        using var admin = MinioServer.Get().AdminClient();
        try
        {
            using var response = admin.GetObjectAsync(target.Bucket, $"{target.Prefix}/{relativePath}").GetAwaiter().GetResult();
            using var copy = new MemoryStream();
            response.ResponseStream.CopyTo(copy);
            return copy.ToArray();
        }
        catch (Amazon.S3.AmazonS3Exception ex) when (ex.StatusCode == System.Net.HttpStatusCode.NotFound)
        {
            return null;
        }
    }

    protected override void PutMoveTarget(MoveTargetConfig target, string relativePath, byte[] data)
    {
        using var admin = MinioServer.Get().AdminClient();
        admin.PutObjectAsync(new Amazon.S3.Model.PutObjectRequest
        {
            BucketName = target.Bucket, Key = $"{target.Prefix}/{relativePath}", InputStream = new MemoryStream(data),
        }).GetAwaiter().GetResult();
    }
}

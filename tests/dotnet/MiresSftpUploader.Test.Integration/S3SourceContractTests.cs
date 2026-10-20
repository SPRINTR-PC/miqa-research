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
        return S3Source.Create(server.Source("contract", bucket, "contract"), server.Credentials);
    }
}

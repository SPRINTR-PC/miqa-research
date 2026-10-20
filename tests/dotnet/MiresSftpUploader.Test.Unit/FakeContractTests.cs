using MiresSftpUploader.Core;
using MiresSftpUploader.Test.Support;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class FakeRemoteContractTests : RemoteContract
{
    protected override IRemote CreateRemote() => new FakeRemote();
}

[TestClass]
public sealed class FakeSourceContractTests : SourceContract
{
    protected override ISource CreateSource(IReadOnlyDictionary<string, byte[]> files)
    {
        var source = new FakeSource("contract");
        foreach (var (path, data) in files) source.Add(path, data);
        return source;
    }
}

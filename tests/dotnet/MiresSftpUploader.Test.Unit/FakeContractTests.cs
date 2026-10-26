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
        _source = source;
        return source;
    }

    private FakeSource? _source;

    protected override MoveTargetConfig CreateMoveTarget() => new() { Action = MoveAction.Move, Path = "/fake/" + Guid.NewGuid().ToString("N") };

    protected override byte[]? ReadMoveTarget(MoveTargetConfig target, string relativePath) => _source!.MovedFile(target, relativePath);

    protected override void PutMoveTarget(MoveTargetConfig target, string relativePath, byte[] data) => _source!.PutMoved(target, relativePath, data);
}

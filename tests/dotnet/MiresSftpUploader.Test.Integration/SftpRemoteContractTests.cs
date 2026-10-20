using MiresSftpUploader.Core;
using MiresSftpUploader.Test.Support;

namespace MiresSftpUploader.Test.Integration;

[TestClass]
[TestCategory("Container")]
public sealed class SftpRemoteContractTests : RemoteContract
{
    [AssemblyCleanup]
    public static async Task StopServer() => await SftpServer.StopAsync();

    protected override string RootDirectory => SftpServer.Get().UploadDirectory;

    protected override IRemote CreateRemote() => new SshNetRemote(SftpServer.Get().Connection());
}

using MiresSftpUploader.Core;

namespace MiresSftpUploader.Test.Support;

/// <summary>An <see cref="IRemoteFactory"/> that hands out one prepared remote (usually a <see cref="FakeRemote"/>).</summary>
public sealed class StaticRemoteFactory(IRemote remote) : IRemoteFactory
{
    public IRemote Create(AppConfig config, Secrets secrets) => remote;
}

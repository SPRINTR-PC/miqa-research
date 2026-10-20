namespace MiresSftpUploader.Core;

/// <summary>A Source could not be built from its configuration (for example its S3 Secrets are not set).</summary>
public sealed class SourceSetupException(string message) : Exception(message);

/// <summary>Builds the <see cref="ISource"/> adapter for a configured Source.</summary>
public static class SourceFactory
{
    public static ISource Create(SourceConfig config, Secrets secrets)
    {
        if (config.Type == SourceType.Directory)
            return new DirectorySource(config.Name!, config.Path!, config.RemotePath);

        var credentials = secrets.S3(config.Name!);
        if (credentials is null)
        {
            var variable = $"MIRES_S3_{Secrets.NormaliseSourceName(config.Name!)}";
            throw new SourceSetupException(
                $"S3 Source '{config.Name}' needs the environment variables {variable}_ACCESS_KEY and {variable}_SECRET_KEY.");
        }
        return S3Source.Create(config, credentials);
    }
}

using Microsoft.Extensions.Logging;

namespace MiresSftpUploader.Core;

/// <summary>
/// The configuration of one Run, read once, and the Engine built from it. <see cref="Engine"/> is null when the
/// configuration has <see cref="Errors"/>.
/// </summary>
public sealed record PreparedUploader(
    AppConfig? Config,
    IReadOnlyList<ConfigError> Errors,
    IReadOnlyList<ConfigError> Warnings,
    SecretStatus Secrets,
    IRunEngine? Engine)
{
    /// <summary>"host:port" for display; empty when no host is configured.</summary>
    public string Destination => Config is null ? "" : UploaderComposition.DestinationKey(Config.Sftp);
}

/// <summary>Reads the configuration and the Secrets and builds an Engine from them. The window and the Headless Run both start here.</summary>
public interface IUploaderRuntime
{
    PreparedUploader Prepare(bool headless);
}

/// <summary>The composition root: configuration, Secrets, Sources, the remote seam and the logger, wired into an <see cref="Engine"/>.</summary>
public sealed class UploaderRuntime(
    Configuration configuration,
    IRemoteFactory remotes,
    ILoggerFactory loggers,
    TimeProvider time,
    CliOptions? cli = null,
    ISourceFactory? sources = null) : IUploaderRuntime
{
    private readonly ISourceFactory _sources = sources ?? new DefaultSourceFactory();

    public PreparedUploader Prepare(bool headless)
    {
        var load = configuration.Load(cli, headless);
        if (load.Config is not { } config)
            return new PreparedUploader(null, load.Errors, load.Warnings, load.Secrets, null);

        var secrets = configuration.LoadSecrets();
        List<ISource> built;
        try
        {
            built = config.Sources.Where(s => s.Enabled).Select(s => _sources.Create(s, secrets)).ToList();
        }
        catch (SourceSetupException ex)
        {
            return new PreparedUploader(config, [.. load.Errors, new ConfigError("Sources", ex.Message)], load.Warnings, load.Secrets, null);
        }
        var engine = new Engine(
            remotes.Create(config, secrets),
            built,
            UploaderComposition.ToEngineSettings(config) with { Redactor = Redactor.From(secrets) },
            new Logger<Engine>(loggers),
            time);
        return new PreparedUploader(config, load.Errors, load.Warnings, load.Secrets, engine);
    }
}

using FellowOakDicom.Network;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Miqa.Infrastructure.Configuration;

namespace Miqa.Service.DicomReceiver;

public class DicomReceiver : BackgroundService
{
    private readonly ILogger<DicomReceiver> _logger;

    public DicomReceiver(ILogger<DicomReceiver> logger)
    {
        _logger = logger;
    }

    protected async override Task ExecuteAsync(CancellationToken stoppingToken)
    {
        if (string.IsNullOrWhiteSpace(MiqaConfiguration.DicomReceiverConfiguration.IncomingDirectory))
            throw new InvalidOperationException("No incoming directory specified in appsettings");
        try
        {
            _logger.LogInformation("Initializing DICOM node");
            _logger.LogDebug("Incoming DICOM-files are stored under {incomingDir}", MiqaConfiguration.DicomReceiverConfiguration.IncomingDirectory);
            using (DicomServerFactory.Create<CStoreSCP>(MiqaConfiguration.DicomReceiverConfiguration.Port))
            {
                _logger.LogInformation("DICOM node started.");
                while (!stoppingToken.IsCancellationRequested)
                {
                    await Task.Delay(1000, stoppingToken);
                }

                _logger.LogInformation("Stopping DICOM node");
            }
        }
        catch (Exception e)
        {
            _logger.LogError(e, "An unhandled exception occured");
            throw;
        }
    }
}
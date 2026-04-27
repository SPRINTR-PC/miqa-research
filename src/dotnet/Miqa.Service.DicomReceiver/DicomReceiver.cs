using FellowOakDicom.Network;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Miqa.Infrastructure.Configuration;

namespace Miqa.Service.DicomReceiver;

public class DicomReceiver(ILogger<DicomReceiver> logger) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        if (string.IsNullOrWhiteSpace(MiqaConfiguration.DicomReceiverConfiguration.IncomingDirectory))
            throw new InvalidOperationException("No incoming directory specified in appsettings");
        try
        {
            logger.LogInformation("Initializing DICOM node");
            logger.LogDebug("Incoming DICOM-files are stored under {incomingDir}", MiqaConfiguration.DicomReceiverConfiguration.IncomingDirectory);
            using (DicomServerFactory.Create<CStoreSCP>(MiqaConfiguration.DicomReceiverConfiguration.Port))
            {
                logger.LogInformation("DICOM node started.");
                while (!stoppingToken.IsCancellationRequested)
                {
                    await Task.Delay(1000, stoppingToken);
                }

                logger.LogInformation("Stopping DICOM node");
            }
        }
        catch (Exception e)
        {
            logger.LogError(e, "An unhandled exception occured");
            throw;
        }
    }
}
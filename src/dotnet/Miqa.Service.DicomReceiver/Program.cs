using FellowOakDicom;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Miqa.Infrastructure.Configuration;
using NLog.Extensions.Logging;
using Microsoft.Extensions.Logging;
using Miqa.Service.DicomReceiver;

ConfigurationHelper configurationHelper = new();

MiqaConfiguration.DicomReceiverConfiguration = configurationHelper.GetDicomReceiverConfiguration();

IHost host = configurationHelper.CreateHostBuilder(args)
    .ConfigureServices(services =>
    {
        new DicomSetupBuilder().RegisterServices(s => s.AddFellowOakDicom().AddLogging(builder =>
        {
            builder.AddNLog(new NLogProviderOptions { CaptureMessageTemplates = true, CaptureMessageProperties = true })
                .SetMinimumLevel(LogLevel.Trace);
        })).Build();
        services.AddHostedService<DicomReceiver>();
    })
    .Build();
    
host.Run();
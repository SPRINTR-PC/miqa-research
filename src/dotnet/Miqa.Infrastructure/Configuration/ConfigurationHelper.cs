using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using NLog.Extensions.Logging;

namespace Miqa.Infrastructure.Configuration;

public interface IConfigurationHelper
{
    DicomReceiverConfiguration GetDicomReceiverConfiguration();
}

public class ConfigurationHelper
{
    public IHostBuilder CreateHostBuilder(string[] args)
    {
        var configuration = GetBaseConfiguration();

        return Host.CreateDefaultBuilder(args)
            .UseWindowsService()
            .ConfigureAppConfiguration((hostingContext, config) =>
            {
                config.AddConfiguration(configuration);
            })
            .ConfigureLogging((hostingContext, logging) =>
            {
                logging.AddConfiguration(hostingContext.Configuration.GetSection("Logging"));
                logging.AddNLog(new NLogProviderOptions
                {
                    CaptureMessageTemplates = true,
                    CaptureMessageProperties = true
                }).SetMinimumLevel(LogLevel.Trace);
            })
            .UseContentRoot(Directory.GetCurrentDirectory());
    }
    
    public DicomReceiverConfiguration GetDicomReceiverConfiguration()
    {
        var configuration = GetBaseConfiguration();
        
        var dicomReceiverConfiguration = new DicomReceiverConfiguration();
        configuration.GetSection(nameof(ConfigurationSection.DicomReceiver)).Bind(dicomReceiverConfiguration);
        return dicomReceiverConfiguration;
    }

    private IConfiguration GetBaseConfiguration()
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .SetBasePath(AppContext.BaseDirectory)
            .AddJsonFile("appsettings.json")
            .AddEnvironmentVariables()
            .Build();

        configuration = EnvironmentVariables.ReplaceConfigurationValuesIfMiqaEnvironmentVariablesExist(configuration);
        
        return configuration;
    }
}
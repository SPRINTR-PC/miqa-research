namespace Miqa.Infrastructure.Configuration;

public class DicomReceiverConfiguration
{
    public string IncomingDirectory { get; set; }
    public string AETitle { get; set; }
    public int Port { get; set; }
    public HashSet<string> AllowedIPAddresses { get; set; } = new HashSet<string>();
}
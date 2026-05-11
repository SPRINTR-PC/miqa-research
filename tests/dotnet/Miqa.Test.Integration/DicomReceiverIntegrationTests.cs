using FellowOakDicom;
using FellowOakDicom.Network;
using FellowOakDicom.Network.Client;
using Microsoft.Extensions.Logging;
using Miqa.Infrastructure.Configuration;
using Miqa.Service.DicomReceiver;
using System.Net;
using System.Net.Sockets;

namespace Miqa.Test.Integration;

[TestClass]
[DoNotParallelize]
public class DicomReceiverIntegrationTests
{
    private static readonly string TestAETitle = "MIQA_TEST";
    private static readonly int TestPort = 11104;
    private static readonly string IncomingDir = Path.Combine(Path.GetTempPath(), "miqa_test_incoming");

    private IDicomServer _server;
    private int _currentPort;
    private static int _portCounter = 11104;
    private DicomReceiverConfiguration _config;

    [TestInitialize]
    public void Initialize()
    {
        _currentPort = Interlocked.Increment(ref _portCounter);

        if (Directory.Exists(IncomingDir))
        {
            try { Directory.Delete(IncomingDir, true); } catch { }
        }
        Directory.CreateDirectory(IncomingDir);

        _config = new DicomReceiverConfiguration
        {
            AETitle = TestAETitle,
            IncomingDirectory = IncomingDir,
            Port = _currentPort,
            AllowedIPAddresses = new HashSet<string>()
        };
        MiqaConfiguration.DicomReceiverConfiguration = _config;

        _server = DicomServerFactory.Create<CStoreSCP>(_currentPort);
    }

    [TestCleanup]
    public void Cleanup()
    {
        _server?.Dispose();
        _server = null;
        if (Directory.Exists(IncomingDir))
        {
            try { Directory.Delete(IncomingDir, true); } catch { }
        }
    }

    [TestMethod]
    public async Task CEcho_ReturnsSuccess()
    {
        var client = DicomClientFactory.Create("127.0.0.1", _currentPort, false, "SCU", TestAETitle);
        bool success = false;
        var request = new DicomCEchoRequest();
        request.OnResponseReceived += (req, response) =>
        {
            if (response.Status == DicomStatus.Success)
            {
                success = true;
            }
        };

        await client.AddRequestAsync(request);
        await client.SendAsync();

        Assert.IsTrue(success, "C-ECHO should return Success");
    }
    
    [TestMethod]
    public async Task Association_WrongCalledAETitle_Rejects()
    {
        _config.AETitle = "MIQA_TEST_NEW";
        var client = DicomClientFactory.Create("127.0.0.1", _currentPort, false, "SCU", "WRONG_AE");

        try
        {
            await SendEchoAsync(client);
            Assert.Fail("Expected association rejection for wrong Called AE Title.");
        }
        catch (DicomAssociationRejectedException)
        {
            // expected
        }
    }

    [TestMethod]
    public async Task Association_InvalidIP_Rejects()
    {
        _config.AllowedIPAddresses = new HashSet<string> { "1.2.3.4" };
        var client = DicomClientFactory.Create("127.0.0.1", _currentPort, false, "SCU", TestAETitle);

        try
        {
            await SendEchoAsync(client);
            Assert.Fail("Expected association rejection for unauthorized IP.");
        }
        catch (DicomAssociationRejectedException)
        {
            // expected
        }
    }

    [TestMethod]
    public async Task Association_ValidIP_Accepts()
    {
        _config.AllowedIPAddresses = new HashSet<string> { "127.0.0.1" };
        var client = DicomClientFactory.Create("127.0.0.1", _currentPort, false, "SCU", TestAETitle);

        var response = await SendEchoAsync(client);

        Assert.AreEqual(DicomStatus.Success, response.Status, "Association should be accepted for authorized IP");
    }
    
    private static async Task<DicomCEchoResponse> SendEchoAsync(IDicomClient client, int timeoutMs = 3000)
    {
        var responseTcs = new TaskCompletionSource<DicomCEchoResponse>(
            TaskCreationOptions.RunContinuationsAsynchronously);

        var request = new DicomCEchoRequest();
        request.OnResponseReceived += (_, response) => responseTcs.TrySetResult(response);

        await client.AddRequestAsync(request);
        await client.SendAsync();

        var completed = await Task.WhenAny(responseTcs.Task, Task.Delay(timeoutMs));
        if (completed != responseTcs.Task)
        {
            throw new TimeoutException("Timed out waiting for C-ECHO response.");
        }

        return await responseTcs.Task;
    }
}

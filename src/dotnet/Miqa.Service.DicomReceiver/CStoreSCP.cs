using FellowOakDicom;
using FellowOakDicom.Network;
using System.Globalization;
using System.Text;
using System.Text.RegularExpressions;
using Microsoft.Extensions.Logging;
using Miqa.Infrastructure.Configuration;

namespace Miqa.Service.DicomReceiver;

public partial class CStoreSCP : DicomService, IDicomServiceProvider, IDicomCStoreProvider, IDicomCEchoProvider
{
    private readonly HashSet<string> _validIps = MiqaConfiguration.DicomReceiverConfiguration.AllowedIPAddresses; 
    private static DateTime ReceiveDataTimer { get; set; }
    private static short ReceiveFilesCounter { get; set; }
    
    private static readonly DicomTransferSyntax[] AcceptedTransferSyntaxes =
    [
        DicomTransferSyntax.ExplicitVRLittleEndian,
        DicomTransferSyntax.ExplicitVRBigEndian,
        DicomTransferSyntax.ImplicitVRLittleEndian
    ];

    private static readonly DicomTransferSyntax[] AcceptedImageTransferSyntaxes =
    [
        // Lossless
        DicomTransferSyntax.JPEGLSLossless,
        DicomTransferSyntax.JPEG2000Lossless,
        DicomTransferSyntax.JPEGProcess14SV1,
        DicomTransferSyntax.JPEGProcess14,
        DicomTransferSyntax.RLELossless,
        

        // Lossy
        DicomTransferSyntax.JPEGLSNearLossless,
        DicomTransferSyntax.JPEG2000Lossy,
        DicomTransferSyntax.JPEGProcess1,
        DicomTransferSyntax.JPEGProcess2_4,
        DicomTransferSyntax.JPIPHTJ2KReferenced,
        DicomTransferSyntax.JPIPHTJ2KReferencedDeflate,
        DicomTransferSyntax.JPIPReferenced,
        DicomTransferSyntax.JPIPReferencedDeflate,

        // Uncompressed
        DicomTransferSyntax.ExplicitVRLittleEndian,
        DicomTransferSyntax.ExplicitVRBigEndian,
        DicomTransferSyntax.ImplicitVRLittleEndian
    ];
    
    public CStoreSCP(INetworkStream stream, Encoding fallbackEncoding, ILogger log, DicomServiceDependencies dependencies) : base(stream, fallbackEncoding, log, dependencies)
    {
        Logger.LogDebug("DicomReceiver constructor with stream and fallbackEncoding");
    }
    
    public Task OnReceiveAssociationRequestAsync(DicomAssociation association)
    {
        if (association.CalledAE != MiqaConfiguration.DicomReceiverConfiguration.AETitle)
            return SendAssociationRejectAsync(
                DicomRejectResult.Permanent,
                DicomRejectSource.ServiceUser,
                DicomRejectReason.CalledAENotRecognized);

        if (_validIps.Count > 0 && !_validIps.Contains("*") && !_validIps.Contains(association.RemoteHost))
        {
            Logger.LogWarning(
                "Received association request from {RemoteHost} ({CallingAE}) which is not in the list of allowed IPs",
                association.RemoteHost, association.CallingAE);
            return SendAssociationRejectAsync(
                DicomRejectResult.Permanent,
                DicomRejectSource.ServiceUser,
                DicomRejectReason.NoReasonGiven);
        }
        
        foreach (var presentationContext in association.PresentationContexts)
        {
            if (presentationContext.AbstractSyntax == DicomUID.Verification) 
                presentationContext.AcceptTransferSyntaxes(AcceptedTransferSyntaxes);
            else if (presentationContext.AbstractSyntax.StorageCategory != DicomStorageCategory.None) 
                presentationContext.AcceptTransferSyntaxes(AcceptedImageTransferSyntaxes);
        }

        ReceiveDataTimer = DateTime.Now;
        ReceiveFilesCounter = 0;

        LogReceivingFilesFromCallingAeCallingIp(Logger, association.CallingAE, association.RemoteHost);

        return SendAssociationAcceptAsync(association);
    }

    public Task OnReceiveAssociationReleaseRequestAsync()
    {
        Logger.LogDebug("Received Association Release Request");
        return SendAssociationReleaseResponseAsync();
    }

    public void OnReceiveAbort(DicomAbortSource source, DicomAbortReason reason)
    {
        Logger.LogInformation("Received abort from '{CallingAE}'", Association.CallingAE);
    }
    
    public void OnConnectionClosed(Exception exception)
    {
        var spentTime = (DateTime.Now - ReceiveDataTimer).TotalSeconds;
        LogHandledReceiveFilesCounterFilesInSpentTimeS(Logger, ReceiveFilesCounter.ToString(), spentTime.ToString(CultureInfo.InvariantCulture));
        ReceiveFilesCounter = 0;

        if (exception != null)
        {
            Logger.LogError(exception: exception, "Connection to {CallingAE} closed with exception", Association.CallingAE);
        }
        else
        {
            Logger.LogInformation("Connection to {CallingAE} closed", Association.CallingAE);
        }
    }

    public async Task<DicomCStoreResponse> OnCStoreRequestAsync(DicomCStoreRequest request)
    {
        ReceiveFilesCounter++;
        LogReceivingFileFromCallingAeAssociation(Logger, Association.CallingAE, Association.RemoteHost);
        
        var status = await SaveToIncomingDirectory(request: request);

        return new DicomCStoreResponse(request, status);
    }

    public Task OnCStoreRequestExceptionAsync(string tempFileName, Exception e)
    {
        Logger.LogError(exception: e, "Could not save incoming file correctly - Exception {message}: {stacktrace}", e.Message, e.StackTrace);
        return Task.CompletedTask;
    }

    public Task<DicomCEchoResponse> OnCEchoRequestAsync(DicomCEchoRequest request)
    {
        LogDicomEchoRequestReceivedFromCallingAeOnRemoteHostRemotePort(Logger, Association.CallingAE, Association.RemoteHost, Association.RemotePort);
        return Task.FromResult(new DicomCEchoResponse(request, DicomStatus.Success));
    }
    
    private async Task<DicomStatus> SaveToIncomingDirectory(DicomCStoreRequest request)
    {
        try
        {
            var regexSearch = new string(Path.GetInvalidFileNameChars());
            var regex = new Regex($"[{Regex.Escape(regexSearch)}]");

            if (!Directory.Exists(MiqaConfiguration.DicomReceiverConfiguration.IncomingDirectory))
                Directory.CreateDirectory(MiqaConfiguration.DicomReceiverConfiguration.IncomingDirectory);

            var filePath = Path.Combine(MiqaConfiguration.DicomReceiverConfiguration.IncomingDirectory,
                regex.Replace($"{Guid.NewGuid()}.dcm", ""));
            await request.File.SaveAsync(filePath);
            
            return DicomStatus.Success;
        }
        catch (Exception ex)
        {
            Logger.LogError(exception: ex,
                "Could not save file to IncomingDirectory {IncomingDirectory}",
                MiqaConfiguration.DicomReceiverConfiguration.IncomingDirectory);
            return DicomStatus.StorageCannotUnderstand;
        }
        
    }

    [LoggerMessage(LogLevel.Information, "DICOM ECHO request received from {CallingAE} on {RemoteHost}:{RemotePort}")]
    static partial void LogDicomEchoRequestReceivedFromCallingAeOnRemoteHostRemotePort(ILogger logger, string callingAe, string remoteHost, int remotePort);

    [LoggerMessage(LogLevel.Debug, "Receiving file from {CallingAE} ({Association})")]
    static partial void LogReceivingFileFromCallingAeAssociation(ILogger logger, string callingAe, string association);

    [LoggerMessage(LogLevel.Information, "Receiving files from {CallingAE} ({CallingIP})")]
    static partial void LogReceivingFilesFromCallingAeCallingIp(ILogger logger, string callingAe, string callingIp);

    [LoggerMessage(LogLevel.Information, "Handled {ReceiveFilesCounter} files in {spentTime} s")]
    static partial void LogHandledReceiveFilesCounterFilesInSpentTimeS(ILogger logger, string receiveFilesCounter, string spentTime);
}
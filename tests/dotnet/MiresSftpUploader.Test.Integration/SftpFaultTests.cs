using System.Net;
using System.Net.Sockets;
using Microsoft.Extensions.Logging.Abstractions;
using MiresSftpUploader.Core;

namespace MiresSftpUploader.Test.Integration;

/// <summary>A TCP relay to the SFTP server that cuts the first connection once it has carried enough upload bytes.</summary>
internal sealed class CuttingProxy : IDisposable
{
    private readonly TcpListener _listener = new(IPAddress.Loopback, 0);
    private readonly CancellationTokenSource _stop = new();
    private readonly SftpServerInfo _server;
    private readonly long _cutAfterBytes;
    private int _connections;

    public CuttingProxy(SftpServerInfo server, long cutAfterBytes)
    {
        _server = server;
        _cutAfterBytes = cutAfterBytes;
        _listener.Start();
        _ = AcceptAsync();
    }

    public int Port => ((IPEndPoint)_listener.LocalEndpoint).Port;
    public int Connections => Volatile.Read(ref _connections);

    private async Task AcceptAsync()
    {
        try
        {
            while (!_stop.IsCancellationRequested)
            {
                var client = await _listener.AcceptTcpClientAsync(_stop.Token);
                var first = Interlocked.Increment(ref _connections) == 1;
                _ = RelayAsync(client, first);
            }
        }
        catch (Exception ex) when (ex is OperationCanceledException or ObjectDisposedException or SocketException) { }
    }

    private async Task RelayAsync(TcpClient client, bool cut)
    {
        using var upstream = new TcpClient();
        try
        {
            await upstream.ConnectAsync(_server.Host, _server.Port, _stop.Token);
            using (client)
            {
                var up = Pump(client.GetStream(), upstream.GetStream(), cut ? _cutAfterBytes : long.MaxValue);
                var down = Pump(upstream.GetStream(), client.GetStream(), long.MaxValue);
                await Task.WhenAny(up, down);
            }
        }
        catch (Exception ex) when (ex is IOException or SocketException or OperationCanceledException or ObjectDisposedException) { }
    }

    private async Task Pump(Stream from, Stream to, long limit)
    {
        var buffer = new byte[16 * 1024];
        long total = 0;
        try
        {
            while (total < limit)
            {
                var n = await from.ReadAsync(buffer, _stop.Token);
                if (n == 0) return;
                await to.WriteAsync(buffer.AsMemory(0, n), _stop.Token);
                total += n;
            }
        }
        catch (Exception ex) when (ex is IOException or SocketException or OperationCanceledException or ObjectDisposedException) { }
    }

    public void Dispose()
    {
        _stop.Cancel();
        _listener.Stop();
    }
}

[TestClass]
[TestCategory("Container")]
public sealed class SftpFaultTests
{
    [TestMethod]
    public async Task Connection_cut_mid_upload_ends_with_a_correct_hash_after_retry_and_no_part_file()
    {
        var server = SftpServer.Get();
        var directory = Directory.CreateTempSubdirectory("mires-cut-").FullName;
        try
        {
            var path = Path.Combine(directory, "slide.bin");
            await SftpHashProofTests.WriteRandomAsync(path, 24 * 1024 * 1024);
            var local = await SftpHashProofTests.HashFileAsync(path);
            var remoteRoot = SftpHashProofTests.NewRemoteRoot(server);

            using var proxy = new CuttingProxy(server, cutAfterBytes: 6 * 1024 * 1024);
            var viaProxy = server.Connection() with { Host = "127.0.0.1", Port = proxy.Port };
            var engine = new Engine(new SshNetRemote(viaProxy), [new DirectorySource("scans", directory)],
                new EngineSettings
                {
                    RemoteRoot = remoteRoot,
                    Retry = new RetrySettings { MaxAttempts = 3, BaseDelay = TimeSpan.Zero, MaxDelay = TimeSpan.Zero },
                },
                NullLogger<Engine>.Instance, TimeProvider.System);

            var result = await engine.RunAsync(new RunOptions(), new Progress<RunEvent>(), CancellationToken.None);

            Assert.AreEqual(0, result.ExitCode, result.Reason);
            Assert.IsTrue(proxy.Connections >= 2, "the first connection was cut, so the retry must have reconnected");
            Assert.AreEqual(local, await SftpServer.RemoteSha256Async(remoteRoot + "/scans/slide.bin"));
            Assert.AreEqual(local, await SftpHashProofTests.ManifestHashAsync(remoteRoot + "/scans/manifest.json", "slide.bin"));
            Assert.IsFalse((await SftpServer.RemoteFilesAsync(remoteRoot)).Any(f => f.EndsWith(".part")), "no .part may remain");
        }
        finally
        {
            Directory.Delete(directory, recursive: true);
        }
    }

    [TestMethod]
    public async Task File_modified_mid_upload_ends_ChangedDuringUpload_with_nothing_renamed()
    {
        var server = SftpServer.Get();
        var directory = Directory.CreateTempSubdirectory("mires-changed-").FullName;
        try
        {
            var path = Path.Combine(directory, "slide.bin");
            await SftpHashProofTests.WriteRandomAsync(path, 8 * 1024 * 1024);
            var remoteRoot = SftpHashProofTests.NewRemoteRoot(server);
            var source = new AppendingSource(new DirectorySource("scans", directory), path);

            var result = await SftpHashProofTests.NewEngine(server, remoteRoot, source)
                .RunAsync(new RunOptions(), new Progress<RunEvent>(), CancellationToken.None);

            Assert.AreEqual(ExitCodes.SomeFilesFailed, result.ExitCode);
            Assert.AreEqual(1, result.Count(FileOutcome.Failed));
            var files = await SftpServer.RemoteFilesAsync(remoteRoot);
            Assert.IsFalse(files.Any(f => f.EndsWith("/slide.bin")), "nothing may be renamed to the final name");
            Assert.IsFalse(files.Any(f => f.EndsWith(".part") && f.Contains("slide.bin")), "the .part must be removed");
            StringAssert.Contains(await SftpServer.RemoteReadTextAsync(remoteRoot + "/scans/manifest.json"), "ChangedDuringUpload");
        }
        finally
        {
            Directory.Delete(directory, recursive: true);
        }
    }

    /// <summary>Appends to the file once its upload has started reading, as another program writing to it would.</summary>
    private sealed class AppendingSource(DirectorySource inner, string path) : ISource
    {
        public string Name => inner.Name;
        public string? RemotePath => inner.RemotePath;
        public IAsyncEnumerable<SourceFile> ListAsync(CancellationToken ct) => inner.ListAsync(ct);
        public Task<SourceFile?> StatAsync(string relativePath, CancellationToken ct) => inner.StatAsync(relativePath, ct);

        public async Task<Stream> OpenReadAsync(string relativePath, CancellationToken ct)
        {
            var stream = await inner.OpenReadAsync(relativePath, ct);
            File.AppendAllText(path, "late write");
            return stream;
        }
    }
}

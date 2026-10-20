using Microsoft.Extensions.Logging;
using MiresSftpUploader.Core;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class RedactingLoggerTests : ConfigurationTestBase
{
    private const string Password = "hunter2-very-secret";

    private (ILoggerFactory Factory, CapturingLoggerProvider Captured) NewFactory()
    {
        var secrets = Create(ValidMachine().ToJsonString(), env: new() { ["MIRES_SFTP_PASSWORD"] = Password }).LoadSecrets();
        var captured = new CapturingLoggerProvider();
        var factory = LoggerFactory.Create(b => b.SetMinimumLevel(LogLevel.Trace).AddProvider(new RedactingLoggerProvider(captured, Redactor.From(secrets))));
        return (factory, captured);
    }

    [TestMethod]
    public void A_Secret_in_a_message_argument_never_reaches_the_inner_log()
    {
        var (factory, captured) = NewFactory();

        factory.CreateLogger("Test").LogWarning("Upload failed: {Reason}", $"permission denied for password {Password}");

        Assert.HasCount(1, captured.Entries);
        Assert.AreEqual(LogLevel.Warning, captured.Entries[0].Level);
        Assert.AreEqual("Upload failed: permission denied for password ***", captured.Entries[0].Message);
    }

    [TestMethod]
    public void A_Secret_in_an_exception_message_or_inner_exception_never_reaches_the_inner_log()
    {
        var (factory, captured) = NewFactory();
        var ex = new InvalidOperationException("outer", new IOException($"auth with {Password} refused"));

        factory.CreateLogger("Test").LogError(ex, "Connect failed");

        var text = captured.Entries.Single().Message;
        StringAssert.Contains(text, "Connect failed");
        StringAssert.Contains(text, "auth with *** refused");
        Assert.DoesNotContain(Password, text);
    }
}

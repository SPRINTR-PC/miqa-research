using Miqa.Infrastructure.Configuration;

namespace Miqa.Test.Integration;

[TestClass]
[DoNotParallelize]
public class ConfigurationIntegrationTests
{
    [TestInitialize]
    public void Setup()
    {
        // Clear environment variables before each test to ensure a clean state
        Environment.SetEnvironmentVariable("MIRES_DicomReceiver__AETitle", null);
        Environment.SetEnvironmentVariable("MIRES_DicomReceiver__Port", null);
        Environment.SetEnvironmentVariable("MIRES_DicomReceiver__IncomingDirectory", null);
    }

    [TestCleanup]
    public void Cleanup()
    {
        // Clear environment variables after each test
        Environment.SetEnvironmentVariable("MIRES_DicomReceiver__AETitle", null);
        Environment.SetEnvironmentVariable("MIRES_DicomReceiver__Port", null);
        Environment.SetEnvironmentVariable("MIRES_DicomReceiver__IncomingDirectory", null);
    }

    [TestMethod]
    public void GetDicomReceiverConfiguration_ShouldReadFromAppSettings()
    {
        // Arrange
        var helper = new ConfigurationHelper();

        // Act
        var config = helper.GetDicomReceiverConfiguration();

        // Assert
        // These values should match what's in src/dotnet/Miqa.Core/appsettings.json
        Assert.AreEqual("MIQA", config.AETitle);
        Assert.AreEqual(104, config.Port);
        Assert.AreEqual("Incoming", config.IncomingDirectory);
    }

    [TestMethod]
    public void GetDicomReceiverConfiguration_ShouldOverrideWithEnvironmentVariables()
    {
        // Arrange
        var helper = new ConfigurationHelper();
        var expectedAeTitle = "OVERRIDDEN_AE";
        var expectedPort = 12345;
        var expectedDir = "OverriddenDir";

        // Using exactly what the code does to filter and map
        Environment.SetEnvironmentVariable("MIRES_DicomReceiver__AETitle", expectedAeTitle);
        Environment.SetEnvironmentVariable("MIRES_DicomReceiver__Port", expectedPort.ToString());
        Environment.SetEnvironmentVariable("MIRES_DicomReceiver__IncomingDirectory", expectedDir);

        // Act
        var config = helper.GetDicomReceiverConfiguration();

        // Assert
        Assert.AreEqual(expectedAeTitle, config.AETitle);
        Assert.AreEqual(expectedPort, config.Port);
        Assert.AreEqual(expectedDir, config.IncomingDirectory);
    }
}

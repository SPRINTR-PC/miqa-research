using MiresSftpUploader.Core;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class SecretCliTests : ConfigurationTestBase
{
    private const string Value = "hunter2-very-secret";

    private sealed record FixedIdentity(string? MachineId, string Account) : IMachineIdentity;

    private string StorePath => Path.Combine(Dir, "user", "secrets.db");

    private (bool Handled, int ExitCode, string Out, string Err) Invoke(string[] args, string? input = Value, IMachineIdentity? identity = null)
    {
        var locations = new ConfigurationLocations(MachinePath, UserPath, new Dictionary<string, string?>(), StorePath, identity ?? new FixedIdentity("machine-1", "alice"));
        var stdout = new StringWriter();
        var stderr = new StringWriter();
        var handled = Cli.TryRun(args, "1.2.3", stdout, stderr, out var exitCode, locations, readSecret: () => input);
        return (handled, exitCode, stdout.ToString(), stderr.ToString());
    }

    [TestMethod]
    public void A_Secret_is_set_from_the_input_and_listed_by_name_and_state_only()
    {
        var set = Invoke(["--set-secret", "sftp-password"]);

        Assert.IsTrue(set.Handled);
        Assert.AreEqual(0, set.ExitCode, set.Err);
        Assert.IsFalse((set.Out + set.Err).Contains(Value));

        var list = Invoke(["--list-secrets"]);

        Assert.AreEqual(0, list.ExitCode, list.Err);
        Assert.AreEqual("sftp-password\tstored", list.Out.Trim());
        Assert.IsFalse((list.Out + list.Err).Contains(Value));
    }

    [TestMethod]
    public void A_Secret_is_cleared_and_no_longer_listed()
    {
        Invoke(["--set-secret", "s3-secret-key:scans"]);

        var cleared = Invoke(["--clear-secret", "s3-secret-key:scans"]);

        Assert.AreEqual(0, cleared.ExitCode, cleared.Err);
        Assert.AreEqual("", Invoke(["--list-secrets"]).Out.Trim());
    }

    [TestMethod]
    public void The_commands_need_no_Machine_Config()
    {
        Assert.IsFalse(File.Exists(MachinePath));

        Assert.AreEqual(0, Invoke(["--set-secret", "sftp-key-passphrase"]).ExitCode);
    }

    [TestMethod]
    [DataRow("--set-secret", "sftp-password", Value)]
    [DataRow("--set-secret", $"sftp-password={Value}", null)]
    [DataRow($"--set-secret=sftp-password", Value, null)]
    public void A_value_given_as_an_argument_is_refused_and_never_stored_or_echoed(string first, string second, string? third)
    {
        string[] args = third is null ? [first, second] : [first, second, third];

        var r = Invoke(args, input: null);

        Assert.AreNotEqual(ExitCodes.Ok, r.ExitCode, r.Out);
        Assert.IsFalse((r.Out + r.Err).Contains(Value), "the value must not be echoed");
        Assert.AreEqual("", Invoke(["--list-secrets"]).Out.Trim(), "nothing was stored");
    }

    [TestMethod]
    public void An_unknown_Secret_name_is_rejected()
    {
        var r = Invoke(["--set-secret", "sftp-pasword"]);

        Assert.AreEqual(ExitCodes.ConfigurationError, r.ExitCode);
        StringAssert.Contains(r.Err, "Unknown Secret");
        Assert.IsFalse(File.Exists(StorePath));
    }

    [TestMethod]
    [DataRow(null)]
    [DataRow("")]
    public void An_empty_value_stores_nothing(string? input)
    {
        var r = Invoke(["--set-secret", "sftp-password"], input);

        Assert.AreEqual(ExitCodes.ConfigurationError, r.ExitCode);
        Assert.AreEqual("", Invoke(["--list-secrets"]).Out.Trim());
    }

    [TestMethod]
    [DataRow("--set-secret", "sftp-password", Value)]
    [DataRow("--set-secret", Value, "x")]
    [DataRow("--set-secret", Value, "--list-secrets")]
    [DataRow("--set-secret=sftp-password", Value, "x")]
    public void The_value_is_never_accepted_as_an_argument_and_never_echoed(string a, string b, string c)
    {
        var r = Invoke([a, b, c], input: null);

        Assert.AreEqual(ExitCodes.ConfigurationError, r.ExitCode);
        Assert.IsFalse((r.Out + r.Err).Contains(Value));
        Assert.AreEqual("", Invoke(["--list-secrets"]).Out.Trim());
    }

    [TestMethod]
    public void Without_a_machine_identifier_the_commands_fail_and_say_why()
    {
        var r = Invoke(["--set-secret", "sftp-password"], identity: new FixedIdentity(null, "alice"));

        Assert.AreEqual(ExitCodes.ConfigurationError, r.ExitCode);
        StringAssert.Contains(r.Err, "machine identifier");
    }

    [TestMethod]
    public void The_help_text_lists_the_Secret_commands()
    {
        var r = Invoke(["--help"]);

        StringAssert.Contains(r.Out, "--set-secret");
        StringAssert.Contains(r.Out, "--clear-secret");
        StringAssert.Contains(r.Out, "--list-secrets");
    }
}

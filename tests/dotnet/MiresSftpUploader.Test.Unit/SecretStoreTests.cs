using MiresSftpUploader.Core;

namespace MiresSftpUploader.Test.Unit;

[TestClass]
public sealed class SecretStoreTests
{
    private string _dir = "";

    [TestInitialize]
    public void Init() => _dir = Directory.CreateTempSubdirectory("secret-store-").FullName;

    [TestCleanup]
    public void Cleanup()
    {
        try { Directory.Delete(_dir, recursive: true); } catch (IOException) { }
    }

    private string StorePath => Path.Combine(_dir, "secrets.db");

    private sealed record FixedIdentity(string? MachineId, string Account) : IMachineIdentity;

    private static readonly FixedIdentity Alice = new("machine-1", "alice");

    [TestMethod]
    public void A_stored_secret_reads_back_and_a_missing_one_is_not_set()
    {
        using var store = SecretStore.Open(StorePath, Alice);

        store.Set("sftp-password", "hunter2-very-secret");

        var found = store.Get("sftp-password");
        Assert.AreEqual(SecretState.Stored, found.State);
        Assert.AreEqual("hunter2-very-secret", found.Value);
        Assert.AreEqual(SecretState.NotSet, store.Get("sftp-key-passphrase").State);
        Assert.IsNull(store.Get("sftp-key-passphrase").Value);
    }

    [TestMethod]
    [DataRow("machine-2", "alice")]
    [DataRow("machine-1", "bob")]
    public void On_another_machine_or_account_the_secret_is_unreadable_not_an_error(string machineId, string account)
    {
        using (var store = SecretStore.Open(StorePath, Alice))
            store.Set("sftp-password", "hunter2-very-secret");

        using var elsewhere = SecretStore.Open(StorePath, new FixedIdentity(machineId, account));

        var found = elsewhere.Get("sftp-password");
        Assert.AreEqual(SecretState.Unreadable, found.State);
        Assert.IsNull(found.Value);
    }

    [TestMethod]
    public void A_value_moved_to_another_name_is_rejected()
    {
        using (var store = SecretStore.Open(StorePath, Alice))
        {
            store.Set("sftp-password", "hunter2-very-secret");
            store.Set("sftp-key-passphrase", "phrase");
        }
        Tamper("UPDATE secret SET value = (SELECT value FROM secret WHERE name = 'sftp-password') WHERE name = 'sftp-key-passphrase'");

        using var reopened = SecretStore.Open(StorePath, Alice);

        Assert.AreEqual(SecretState.Unreadable, reopened.Get("sftp-key-passphrase").State);
        Assert.AreEqual(SecretState.Stored, reopened.Get("sftp-password").State);
    }

    [TestMethod]
    [DataRow("UPDATE secret SET value = x'0102'")]
    [DataRow("UPDATE secret SET value = x''")]
    [DataRow("UPDATE secret SET value = 'plain text'")]
    [DataRow("UPDATE secret SET value = CAST(substr(value, 1, length(value) - 1) || x'00' AS BLOB)")]
    public void A_damaged_value_is_unreadable_not_an_error(string damage)
    {
        using (var store = SecretStore.Open(StorePath, Alice))
            store.Set("sftp-password", "hunter2-very-secret");
        Tamper(damage);

        using var reopened = SecretStore.Open(StorePath, Alice);

        Assert.AreEqual(SecretState.Unreadable, reopened.Get("sftp-password").State);
    }

    private void Tamper(string sql)
    {
        using var connection = new Microsoft.Data.Sqlite.SqliteConnection($"Data Source={StorePath};Pooling=False");
        connection.Open();
        using var command = connection.CreateCommand();
        command.CommandText = sql;
        command.ExecuteNonQuery();
    }

    [TestMethod]
    [DataRow(null)]
    [DataRow("")]
    [DataRow("   ")]
    public void Without_a_machine_identifier_the_store_is_unavailable_and_creates_nothing(string? machineId)
    {
        var e = Assert.ThrowsExactly<SecretStoreUnavailableException>(() => SecretStore.Open(StorePath, new FixedIdentity(machineId, "alice")));

        StringAssert.Contains(e.Message, "machine identifier");
        Assert.IsFalse(File.Exists(StorePath));
    }

    [TestMethod]
    public void A_secret_can_be_replaced_and_cleared()
    {
        using var store = SecretStore.Open(StorePath, Alice);
        store.Set("sftp-password", "old");

        store.Set("sftp-password", "new");
        Assert.AreEqual("new", store.Get("sftp-password").Value);

        store.Clear("sftp-password");
        Assert.AreEqual(SecretState.NotSet, store.Get("sftp-password").State);
        store.Clear("sftp-password");
    }

    [TestMethod]
    public void Listing_gives_names_and_states_in_name_order_and_never_values()
    {
        using (var store = SecretStore.Open(StorePath, Alice))
        {
            store.Set("sftp-password", "hunter2-very-secret");
            store.Set("s3-secret-key:scans", "s3-secret");
        }
        Tamper("UPDATE secret SET value = x'00' WHERE name = 's3-secret-key:scans'");

        using var reopened = SecretStore.Open(StorePath, Alice);
        var listed = reopened.List();

        CollectionAssert.AreEqual(
            new[] { ("s3-secret-key:scans", SecretState.Unreadable), ("sftp-password", SecretState.Stored) },
            listed.Select(l => (l.Name, l.State)).ToArray());
        Assert.IsFalse(string.Concat(listed.Select(l => l.ToString())).Contains("hunter2"));
    }

    [TestMethod]
    public void On_Unix_the_file_is_readable_by_its_owner_only()
    {
        if (OperatingSystem.IsWindows()) Assert.Inconclusive("Windows relies on the user-profile ACL.");
        using var store = SecretStore.Open(StorePath, Alice);
        store.Set("sftp-password", "hunter2-very-secret");

        Assert.AreEqual(UnixFileMode.UserRead | UnixFileMode.UserWrite, File.GetUnixFileMode(StorePath));
    }

    [TestMethod]
    public void The_file_never_holds_the_plaintext_and_the_secret_survives_reopening()
    {
        const string secret = "hunter2-very-secret";
        using (var store = SecretStore.Open(StorePath, Alice))
            store.Set("sftp-password", secret);

        var raw = System.Text.Encoding.Latin1.GetString(File.ReadAllBytes(StorePath));
        Assert.IsFalse(raw.Contains(secret));
        using var reopened = SecretStore.Open(StorePath, Alice);
        Assert.AreEqual(secret, reopened.Get("sftp-password").Value);
    }
}

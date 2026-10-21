using System.Security.Cryptography;
using System.Text;
using Microsoft.Data.Sqlite;

namespace MiresSftpUploader.Core;

/// <summary>What the Secret Store key is derived from: the machine and the account. A seam so tests can change either.</summary>
public interface IMachineIdentity
{
    /// <summary>The OS machine identifier, or null when the machine has no stable one.</summary>
    string? MachineId { get; }
    string Account { get; }
}

public enum SecretState { NotSet, Stored, Unreadable }

public sealed record SecretLookup(SecretState State, string? Value)
{
    public override string ToString() => $"SecretLookup {{ {State} }}";
}

public sealed record StoredSecret(string Name, SecretState State);

public sealed class SecretStoreUnavailableException(string message) : Exception(message);

/// <summary>
/// The per-account record of Secrets. Values are kept apart from the Upload State and can be read only by the same
/// account on the same machine.
/// </summary>
public sealed class SecretStore : IDisposable
{
    internal const string NoMachineIdentifierMessage =
        "This machine has no stable machine identifier, so the Secret Store is unavailable. Supply Secrets as environment variables instead.";

    private const int NonceSize = 12;
    private const int TagSize = 16;

    private readonly SqliteConnection _connection;
    private readonly byte[] _key;

    private SecretStore(SqliteConnection connection, byte[] key)
    {
        _connection = connection;
        _key = key;
    }

    /// <exception cref="SecretStoreUnavailableException">The machine has no stable identifier to derive the key from.</exception>
    public static SecretStore Open(string path, IMachineIdentity identity)
    {
        if (string.IsNullOrWhiteSpace(identity.MachineId))
            throw new SecretStoreUnavailableException(NoMachineIdentifierMessage);
        var directory = Path.GetDirectoryName(Path.GetFullPath(path));
        if (!string.IsNullOrEmpty(directory)) Directory.CreateDirectory(directory);
        // Created owner-only before SQLite can create it with the umask; SQLite's journal copies the database file's mode.
        if (!OperatingSystem.IsWindows() && !File.Exists(path))
            new FileStream(path, new FileStreamOptions
            {
                Mode = FileMode.CreateNew,
                Access = FileAccess.Write,
                UnixCreateMode = UnixFileMode.UserRead | UnixFileMode.UserWrite,
            }).Dispose();
        var connection = UploadStateStore.OpenConnection(path);
        using var create = connection.CreateCommand();
        create.CommandText = "CREATE TABLE IF NOT EXISTS secret (name TEXT PRIMARY KEY, value BLOB NOT NULL); CREATE TABLE IF NOT EXISTS meta (salt BLOB NOT NULL)";
        create.ExecuteNonQuery();
        return new SecretStore(connection, DeriveKey(connection, identity));
    }

    private static byte[] DeriveKey(SqliteConnection connection, IMachineIdentity identity)
    {
        using var read = connection.CreateCommand();
        read.CommandText = "SELECT salt FROM meta";
        if (read.ExecuteScalar() is not byte[] salt)
        {
            salt = RandomNumberGenerator.GetBytes(32);
            using var insert = connection.CreateCommand();
            insert.CommandText = "INSERT INTO meta (salt) VALUES ($salt)";
            insert.Parameters.AddWithValue("$salt", salt);
            insert.ExecuteNonQuery();
        }
        var material = Encoding.UTF8.GetBytes($"{identity.MachineId}\0{identity.Account}");
        return HKDF.DeriveKey(HashAlgorithmName.SHA256, material, 32, salt, "MiresSftpUploader.SecretStore.v1"u8.ToArray());
    }

    public void Set(string name, string value)
    {
        using var command = _connection.CreateCommand();
        command.CommandText = "INSERT OR REPLACE INTO secret (name, value) VALUES ($name, $value)";
        command.Parameters.AddWithValue("$name", name);
        command.Parameters.AddWithValue("$value", Encrypt(name, value));
        command.ExecuteNonQuery();
    }

    public void Clear(string name)
    {
        using var command = _connection.CreateCommand();
        command.CommandText = "DELETE FROM secret WHERE name = $name";
        command.Parameters.AddWithValue("$name", name);
        command.ExecuteNonQuery();
    }

    /// <summary>The name and state of every stored Secret, ordered by name. Never the values.</summary>
    public IReadOnlyList<StoredSecret> List()
    {
        using var command = _connection.CreateCommand();
        command.CommandText = "SELECT name FROM secret ORDER BY name";
        using var reader = command.ExecuteReader();
        var names = new List<string>();
        while (reader.Read()) names.Add(reader.GetString(0));
        return names.Select(n => new StoredSecret(n, Get(n).State)).ToList();
    }

    public SecretLookup Get(string name)
    {
        using var command = _connection.CreateCommand();
        command.CommandText = "SELECT value FROM secret WHERE name = $name";
        command.Parameters.AddWithValue("$name", name);
        var stored = command.ExecuteScalar();
        if (stored is null) return new SecretLookup(SecretState.NotSet, null);
        try
        {
            return stored is byte[] { Length: >= NonceSize + TagSize } blob
                ? new SecretLookup(SecretState.Stored, Decrypt(name, blob))
                : new SecretLookup(SecretState.Unreadable, null);
        }
        catch (CryptographicException)
        {
            return new SecretLookup(SecretState.Unreadable, null);
        }
    }

    // The name is bound in as associated data, so a value cannot be moved to another row.
    private byte[] Encrypt(string name, string value)
    {
        var plain = Encoding.UTF8.GetBytes(value);
        var blob = new byte[NonceSize + plain.Length + TagSize];
        var nonce = blob.AsSpan(0, NonceSize);
        RandomNumberGenerator.Fill(nonce);
        using var aes = new AesGcm(_key, TagSize);
        aes.Encrypt(nonce, plain, blob.AsSpan(NonceSize, plain.Length), blob.AsSpan(NonceSize + plain.Length, TagSize), Encoding.UTF8.GetBytes(name));
        return blob;
    }

    private string Decrypt(string name, byte[] blob)
    {
        var cipherLength = blob.Length - NonceSize - TagSize;
        var plain = new byte[cipherLength];
        using var aes = new AesGcm(_key, TagSize);
        aes.Decrypt(blob.AsSpan(0, NonceSize), blob.AsSpan(NonceSize, cipherLength), blob.AsSpan(NonceSize + cipherLength, TagSize), plain, Encoding.UTF8.GetBytes(name));
        return Encoding.UTF8.GetString(plain);
    }

    public void Dispose() => _connection.Dispose();
}

using System.Buffers.Binary;
using System.Security.Cryptography;
using System.Text;

namespace MiresSftpUploader.Core;

/// <summary>
/// Writes a zip whose bytes depend only on the entry names and contents: stored entries (no compression), UTF-8 names,
/// a fixed DOS timestamp (1980-01-01 00:00:00), fixed attributes and version fields, a data descriptor per entry, and Zip64
/// structures exactly where sizes or offsets require them. Nothing here reads the clock, the OS or the locale, so every
/// OS produces the same bytes. The SHA-256 of the whole zip is taken while it is written.
/// </summary>
internal sealed class DeterministicZipWriter : IDisposable
{
    private const uint LocalHeaderSignature = 0x04034b50;
    private const uint DescriptorSignature = 0x08074b50;
    private const uint CentralHeaderSignature = 0x02014b50;
    private const uint EndOfCentralDirectorySignature = 0x06054b50;
    private const uint Zip64EndSignature = 0x06064b50;
    private const uint Zip64LocatorSignature = 0x07064b50;

    private const ushort FlagsUtf8WithDescriptor = 0x0808;
    private const ushort DosDate1980 = 0x0021; // 1980-01-01
    private const ushort DosTime = 0;
    private const ushort VersionNeeded = 20;
    private const ushort VersionNeededZip64 = 45;
    private const ushort VersionMadeBy = (3 << 8) | 45; // Unix, 4.5
    private const uint ExternalAttributes = 0x81A4u << 16; // regular file, mode 0644
    private const uint Max32 = 0xFFFFFFFF;

    private readonly Stream _output;
    private readonly IncrementalHash _hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
    private readonly List<CentralEntry> _entries = [];
    private long _position;

    public DeterministicZipWriter(Stream output) => _output = output;

    public long Length => _position;

    /// <summary>
    /// Appends one stored entry, reading <paramref name="content"/> once. <paramref name="declaredSize"/> (from the listing)
    /// decides whether the entry needs Zip64; the caller must compare the returned length with it.
    /// </summary>
    /// <returns>The number of content bytes actually read.</returns>
    public async Task<long> AddAsync(string name, long declaredSize, Stream content, CancellationToken cancellationToken)
    {
        var nameBytes = Encoding.UTF8.GetBytes(name);
        var zip64 = declaredSize >= Max32;
        var offset = _position;

        var header = new byte[30 + nameBytes.Length + (zip64 ? 20 : 0)];
        var span = header.AsSpan();
        BinaryPrimitives.WriteUInt32LittleEndian(span, LocalHeaderSignature);
        BinaryPrimitives.WriteUInt16LittleEndian(span[4..], zip64 ? VersionNeededZip64 : VersionNeeded);
        BinaryPrimitives.WriteUInt16LittleEndian(span[6..], FlagsUtf8WithDescriptor);
        BinaryPrimitives.WriteUInt16LittleEndian(span[8..], 0); // stored
        BinaryPrimitives.WriteUInt16LittleEndian(span[10..], DosTime);
        BinaryPrimitives.WriteUInt16LittleEndian(span[12..], DosDate1980);
        BinaryPrimitives.WriteUInt32LittleEndian(span[14..], 0); // CRC follows in the descriptor
        BinaryPrimitives.WriteUInt32LittleEndian(span[18..], zip64 ? Max32 : 0);
        BinaryPrimitives.WriteUInt32LittleEndian(span[22..], zip64 ? Max32 : 0);
        BinaryPrimitives.WriteUInt16LittleEndian(span[26..], (ushort)nameBytes.Length);
        BinaryPrimitives.WriteUInt16LittleEndian(span[28..], (ushort)(zip64 ? 20 : 0));
        nameBytes.CopyTo(span[30..]);
        if (zip64)
        {
            var extra = span[(30 + nameBytes.Length)..];
            BinaryPrimitives.WriteUInt16LittleEndian(extra, 1);
            BinaryPrimitives.WriteUInt16LittleEndian(extra[2..], 16);
            // sizes stay zero: the real ones are in the descriptor
        }
        await WriteAsync(header, cancellationToken);

        uint crc = 0;
        long size = 0;
        var buffer = new byte[81920];
        int read;
        while ((read = await content.ReadAsync(buffer, cancellationToken)) > 0)
        {
            crc = Crc32.Update(crc, buffer.AsSpan(0, read));
            await WriteAsync(buffer.AsMemory(0, read), cancellationToken);
            size += read;
        }

        var descriptor = new byte[zip64 ? 24 : 16];
        BinaryPrimitives.WriteUInt32LittleEndian(descriptor, DescriptorSignature);
        BinaryPrimitives.WriteUInt32LittleEndian(descriptor.AsSpan(4), crc);
        if (zip64)
        {
            BinaryPrimitives.WriteUInt64LittleEndian(descriptor.AsSpan(8), (ulong)size);
            BinaryPrimitives.WriteUInt64LittleEndian(descriptor.AsSpan(16), (ulong)size);
        }
        else
        {
            BinaryPrimitives.WriteUInt32LittleEndian(descriptor.AsSpan(8), (uint)size);
            BinaryPrimitives.WriteUInt32LittleEndian(descriptor.AsSpan(12), (uint)size);
        }
        await WriteAsync(descriptor, cancellationToken);

        _entries.Add(new CentralEntry(nameBytes, crc, size, offset, zip64));
        return size;
    }

    /// <summary>Writes the central directory and returns the SHA-256 (lower-case hex) of the finished zip.</summary>
    public async Task<string> FinishAsync(CancellationToken cancellationToken)
    {
        var directoryOffset = _position;
        foreach (var e in _entries) await WriteAsync(CentralRecord(e), cancellationToken);
        var directorySize = _position - directoryOffset;

        var needZip64End = _entries.Count >= 0xFFFF || directoryOffset >= Max32 || directorySize >= Max32;
        if (needZip64End)
        {
            var zip64End = new byte[56 + 20];
            var s = zip64End.AsSpan();
            BinaryPrimitives.WriteUInt32LittleEndian(s, Zip64EndSignature);
            BinaryPrimitives.WriteUInt64LittleEndian(s[4..], 44);
            BinaryPrimitives.WriteUInt16LittleEndian(s[12..], VersionMadeBy);
            BinaryPrimitives.WriteUInt16LittleEndian(s[14..], VersionNeededZip64);
            BinaryPrimitives.WriteUInt64LittleEndian(s[24..], (ulong)_entries.Count);
            BinaryPrimitives.WriteUInt64LittleEndian(s[32..], (ulong)_entries.Count);
            BinaryPrimitives.WriteUInt64LittleEndian(s[40..], (ulong)directorySize);
            BinaryPrimitives.WriteUInt64LittleEndian(s[48..], (ulong)directoryOffset);
            BinaryPrimitives.WriteUInt32LittleEndian(s[56..], Zip64LocatorSignature);
            BinaryPrimitives.WriteUInt64LittleEndian(s[64..], (ulong)_position);
            BinaryPrimitives.WriteUInt32LittleEndian(s[72..], 1);
            await WriteAsync(zip64End, cancellationToken);
        }

        var end = new byte[22];
        var span = end.AsSpan();
        BinaryPrimitives.WriteUInt32LittleEndian(span, EndOfCentralDirectorySignature);
        var count = needZip64End ? (ushort)0xFFFF : (ushort)_entries.Count;
        BinaryPrimitives.WriteUInt16LittleEndian(span[8..], count);
        BinaryPrimitives.WriteUInt16LittleEndian(span[10..], count);
        BinaryPrimitives.WriteUInt32LittleEndian(span[12..], needZip64End ? Max32 : (uint)directorySize);
        BinaryPrimitives.WriteUInt32LittleEndian(span[16..], needZip64End ? Max32 : (uint)directoryOffset);
        await WriteAsync(end, cancellationToken);

        await _output.FlushAsync(cancellationToken);
        return Convert.ToHexStringLower(_hash.GetHashAndReset());
    }

    private static byte[] CentralRecord(CentralEntry e)
    {
        var offsetBig = e.Offset >= Max32;
        var extraLength = (e.Zip64 ? 16 : 0) + (offsetBig ? 8 : 0);
        if (extraLength > 0) extraLength += 4;
        var record = new byte[46 + e.Name.Length + extraLength];
        var s = record.AsSpan();
        BinaryPrimitives.WriteUInt32LittleEndian(s, CentralHeaderSignature);
        BinaryPrimitives.WriteUInt16LittleEndian(s[4..], VersionMadeBy);
        BinaryPrimitives.WriteUInt16LittleEndian(s[6..], extraLength > 0 ? VersionNeededZip64 : VersionNeeded);
        BinaryPrimitives.WriteUInt16LittleEndian(s[8..], FlagsUtf8WithDescriptor);
        BinaryPrimitives.WriteUInt16LittleEndian(s[10..], 0);
        BinaryPrimitives.WriteUInt16LittleEndian(s[12..], DosTime);
        BinaryPrimitives.WriteUInt16LittleEndian(s[14..], DosDate1980);
        BinaryPrimitives.WriteUInt32LittleEndian(s[16..], e.Crc);
        BinaryPrimitives.WriteUInt32LittleEndian(s[20..], e.Zip64 ? Max32 : (uint)e.Size);
        BinaryPrimitives.WriteUInt32LittleEndian(s[24..], e.Zip64 ? Max32 : (uint)e.Size);
        BinaryPrimitives.WriteUInt16LittleEndian(s[28..], (ushort)e.Name.Length);
        BinaryPrimitives.WriteUInt16LittleEndian(s[30..], (ushort)extraLength);
        BinaryPrimitives.WriteUInt32LittleEndian(s[38..], ExternalAttributes);
        BinaryPrimitives.WriteUInt32LittleEndian(s[42..], offsetBig ? Max32 : (uint)e.Offset);
        e.Name.CopyTo(s[46..]);
        if (extraLength > 0)
        {
            var extra = s[(46 + e.Name.Length)..];
            BinaryPrimitives.WriteUInt16LittleEndian(extra, 1);
            BinaryPrimitives.WriteUInt16LittleEndian(extra[2..], (ushort)(extraLength - 4));
            var at = 4;
            if (e.Zip64)
            {
                BinaryPrimitives.WriteUInt64LittleEndian(extra[at..], (ulong)e.Size);
                BinaryPrimitives.WriteUInt64LittleEndian(extra[(at + 8)..], (ulong)e.Size);
                at += 16;
            }
            if (offsetBig) BinaryPrimitives.WriteUInt64LittleEndian(extra[at..], (ulong)e.Offset);
        }
        return record;
    }

    private async ValueTask WriteAsync(ReadOnlyMemory<byte> bytes, CancellationToken cancellationToken)
    {
        _hash.AppendData(bytes.Span);
        await _output.WriteAsync(bytes, cancellationToken);
        _position += bytes.Length;
    }

    public void Dispose() => _hash.Dispose();

    private sealed record CentralEntry(byte[] Name, uint Crc, long Size, long Offset, bool Zip64);

    private static class Crc32
    {
        private static readonly uint[] Table = Build();

        private static uint[] Build()
        {
            var table = new uint[256];
            for (uint i = 0; i < 256; i++)
            {
                var c = i;
                for (var k = 0; k < 8; k++) c = (c & 1) != 0 ? 0xEDB88320 ^ (c >> 1) : c >> 1;
                table[i] = c;
            }
            return table;
        }

        public static uint Update(uint crc, ReadOnlySpan<byte> data)
        {
            var c = ~crc;
            foreach (var b in data) c = Table[(c ^ b) & 0xFF] ^ (c >> 8);
            return ~c;
        }
    }
}

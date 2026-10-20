namespace MiresSftpUploader.Core;

/// <summary>One file going into an Archive: where it comes from, and its name inside the zip.</summary>
internal sealed record ArchiveMemberSpec(SourceFile File, string EntryName);

/// <summary>
/// Outcome of building one Archive in the Staging Area. Either <see cref="Failure"/> is set (and no zip remains),
/// or the zip is complete with the SHA-256 of every member, keyed by its relative path in the Source.
/// </summary>
internal sealed record ArchiveBuild(
    string? ZipSha256, long ZipSize, IReadOnlyDictionary<string, string> MemberHashes, string? Failure)
{
    public static ArchiveBuild Failed(string reason) => new(null, 0, new Dictionary<string, string>(), reason);
}

/// <summary>Builds an Archive: reads each member once, feeding the hash and the zip entry from the same pass.</summary>
internal static class ArchiveBuilder
{
    public const string ChangedDuringArchive = "ChangedDuringArchive";

    public static async Task<ArchiveBuild> BuildAsync(
        string zipPath, ISource source, IReadOnlyList<ArchiveMemberSpec> members, CancellationToken cancellationToken)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(zipPath)!);
        var hashes = new Dictionary<string, string>(StringComparer.Ordinal);
        string? failure = null;
        string zipSha = "";
        long zipSize = 0;

        try
        {
            await using (var output = new FileStream(zipPath, FileMode.Create, FileAccess.Write, FileShare.None, 81920, FileOptions.Asynchronous))
            using (var zip = new DeterministicZipWriter(output))
            {
                foreach (var member in members.OrderBy(m => m.EntryName, StringComparer.Ordinal))
                {
                    failure = await AddMemberAsync(zip, source, member, hashes, cancellationToken);
                    if (failure is not null) break;
                }
                if (failure is null)
                {
                    zipSha = await zip.FinishAsync(cancellationToken);
                    zipSize = zip.Length;
                }
            }
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            failure = $"Archive could not be written: {ex.Message}";
        }

        if (failure is not null)
        {
            TryDelete(zipPath);
            return ArchiveBuild.Failed(failure);
        }
        return new ArchiveBuild(zipSha, zipSize, hashes, null);
    }

    private static async Task<string?> AddMemberAsync(
        DeterministicZipWriter zip, ISource source, ArchiveMemberSpec member, Dictionary<string, string> hashes, CancellationToken ct)
    {
        var path = member.File.RelativePath;
        var before = await source.StatAsync(path, ct);
        if (before is null) return $"{ChangedDuringArchive}: {path} disappeared";
        if (Changed(member.File, before)) return $"{ChangedDuringArchive}: {path} changed before it was read";

        long read;
        string hash;
        try
        {
            await using var raw = await source.OpenReadAsync(path, ct);
            await using var hashing = new HashingReadStream(raw);
            read = await zip.AddAsync(member.EntryName, member.File.Size, hashing, ct);
            hash = hashing.FinishHash();
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            return $"Unreadable: {path}: {ex.Message}";
        }

        var after = await source.StatAsync(path, ct);
        if (read != member.File.Size || after is null || Changed(member.File, after))
            return $"{ChangedDuringArchive}: {path} changed while it was read";
        hashes[path] = hash;
        return null;
    }

    private static bool Changed(SourceFile expected, SourceFile actual) =>
        expected.Size != actual.Size || expected.Modified != actual.Modified;

    private static void TryDelete(string path)
    {
        try { File.Delete(path); } catch (IOException) { } catch (UnauthorizedAccessException) { }
    }
}

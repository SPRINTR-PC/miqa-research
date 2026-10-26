namespace MiresSftpUploader.Core;

/// <summary>Compares the configured Host Key Fingerprint with what a server presents.</summary>
public static class HostKeyFingerprint
{
    /// <summary>
    /// True when <paramref name="configured"/> names the presented key. Accepts the SHA256 form (base64, case-sensitive)
    /// or the MD5 form (colon-separated hex, case-insensitive), each with or without its <c>SHA256:</c> / <c>MD5:</c> prefix.
    /// </summary>
    /// <param name="presentedSha256">Base64 SHA-256 of the key, without prefix or padding (the form the ssh command prints).</param>
    /// <param name="presentedMd5">Colon-separated hex MD5 of the key, without prefix.</param>
    public static bool Matches(string? configured, string presentedSha256, string presentedMd5)
    {
        var value = configured?.Trim() ?? "";
        if (value.Length == 0) return false;

        if (value.StartsWith("MD5:", StringComparison.OrdinalIgnoreCase))
            return MatchesMd5(value[4..], presentedMd5);
        if (value.StartsWith("SHA256:", StringComparison.OrdinalIgnoreCase))
            return MatchesSha256(value[7..], presentedSha256);

        return value.Contains(':')
            ? MatchesMd5(value, presentedMd5)
            : MatchesSha256(value, presentedSha256);
    }

    private static bool MatchesSha256(string configured, string presented) =>
        string.Equals(configured.Trim().TrimEnd('='), presented.TrimEnd('='), StringComparison.Ordinal);

    private static bool MatchesMd5(string configured, string presented) =>
        string.Equals(configured.Trim(), presented, StringComparison.OrdinalIgnoreCase);
}

using System;
using System.Globalization;

namespace MiresSftpUploader.ViewModels;

/// <summary>
/// Text for sizes, Upload Speed and Upload Time, shared by the Avalonia pages and the terminal interface so they cannot disagree.
/// Units are binary (KiB, MiB, GiB; MiB/s) and numbers use the invariant culture (a dot).
/// </summary>
public static class TransferFormat
{
    private static readonly CultureInfo Culture = CultureInfo.InvariantCulture;

    /// <summary>A size as <c>12.4 MiB</c> (one decimal at most; GiB, MiB, KiB, else <c>512 bytes</c>).</summary>
    public static string Size(long bytes) => bytes switch
    {
        >= 1L << 30 => $"{(bytes / (double)(1L << 30)).ToString("0.#", Culture)} GiB",
        >= 1L << 20 => $"{(bytes / (double)(1L << 20)).ToString("0.#", Culture)} MiB",
        >= 1L << 10 => $"{(bytes / (double)(1L << 10)).ToString("0.#", Culture)} KiB",
        _ => $"{bytes} bytes",
    };

    /// <summary>An Upload Speed given in bytes per second as <c>3.1 MiB/s</c>; <c>&lt;0.1 MiB/s</c> for a speed that would round to zero; <c>0 MiB/s</c> for zero.</summary>
    public static string Speed(double bytesPerSecond)
    {
        if (bytesPerSecond <= 0) return "0 MiB/s";
        var mib = Math.Round(bytesPerSecond / (1 << 20), 1, MidpointRounding.AwayFromZero);
        return mib <= 0 ? "<0.1 MiB/s" : $"{mib.ToString("0.0", Culture)} MiB/s";
    }

    /// <summary>An Upload Time as <c>&lt;1 s</c>, <c>3 s</c> or <c>1 min 12 s</c> (whole seconds, rounded).</summary>
    public static string Duration(TimeSpan time)
    {
        if (time < TimeSpan.FromSeconds(1)) return "<1 s";
        var seconds = (long)Math.Round(time.TotalSeconds, MidpointRounding.AwayFromZero);
        return seconds < 60 ? $"{seconds} s" : $"{seconds / 60} min {seconds % 60} s";
    }

    /// <summary>What a finished file delivered: <c>12.4 MiB in 3 s</c>.</summary>
    public static string Finished(long bytesSent, TimeSpan uploadTime) => $"{Size(bytesSent)} in {Duration(uploadTime)}";

    /// <summary>An Upload Time stored in milliseconds (the Run History) as <c>&lt;1 s</c>, <c>3 s</c> or <c>1 min 12 s</c>.</summary>
    public static string Duration(long uploadMs) => Duration(TimeSpan.FromMilliseconds(uploadMs));

    /// <summary>What a file in the Run History delivered: <c>12.4 MiB in 3 s</c>.</summary>
    public static string Sent(long bytes, long uploadMs) => $"{Size(bytes)} in {Duration(uploadMs)}";

    /// <summary>The average speed of a finished file, <c>4.1 MiB/s</c>: bytes divided by the Upload Time; empty when the Upload Time is zero.</summary>
    public static string AverageSpeed(long bytes, long uploadMs) =>
        uploadMs <= 0 ? "" : Speed(bytes * 1000.0 / uploadMs);
}

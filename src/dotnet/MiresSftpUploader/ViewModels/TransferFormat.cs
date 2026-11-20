using System;
using System.Globalization;

namespace MiresSftpUploader.ViewModels;

/// <summary>The wording of transferred bytes, Upload Time and average speed in the Run History (binary units, as everywhere in the uploader).</summary>
internal static class TransferFormat
{
    public static string Size(long bytes) => bytes switch
    {
        >= 1L << 30 => $"{(bytes / (double)(1L << 30)).ToString("0.#", CultureInfo.InvariantCulture)} GiB",
        >= 1L << 20 => $"{(bytes / (double)(1L << 20)).ToString("0.#", CultureInfo.InvariantCulture)} MiB",
        >= 1L << 10 => $"{(bytes / (double)(1L << 10)).ToString("0.#", CultureInfo.InvariantCulture)} KiB",
        _ => $"{bytes} bytes",
    };

    /// <summary>Under 1 s is "&lt;1 s", then "3 s", and from a minute on "1 min 12 s".</summary>
    public static string Duration(long uploadMs)
    {
        if (uploadMs < 1000) return "<1 s";
        var seconds = (long)Math.Round(uploadMs / 1000.0, MidpointRounding.AwayFromZero);
        return seconds >= 60 ? $"{seconds / 60} min {seconds % 60} s" : $"{seconds} s";
    }

    /// <summary>"12.4 MiB in 3 s".</summary>
    public static string Sent(long bytes, long uploadMs) => $"{Size(bytes)} in {Duration(uploadMs)}";

    /// <summary>"4.1 MiB/s": bytes divided by the Upload Time; empty when the Upload Time is zero.</summary>
    public static string AverageSpeed(long bytes, long uploadMs) =>
        uploadMs <= 0 ? "" : $"{Size((long)(bytes * 1000.0 / uploadMs))}/s";
}

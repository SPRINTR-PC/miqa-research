namespace MiresSftpUploader.Core;

/// <summary>
/// Replaces the value of every Secret with <c>***</c> in text about to be logged. Built from a <see cref="Secrets"/>
/// snapshot, so it knows the exact values and needs no pattern guessing.
/// </summary>
public sealed class Redactor
{
    public const string Mask = "***";

    private readonly string[] _values;

    private Redactor(IEnumerable<string> values) =>
        _values = values.Where(v => v.Length > 0).Distinct(StringComparer.Ordinal).OrderByDescending(v => v.Length).ToArray();

    public static Redactor From(Secrets secrets) => new(secrets.Values());

    public static Redactor None { get; } = new([]);

    public string Redact(string? text)
    {
        if (string.IsNullOrEmpty(text)) return "";
        foreach (var value in _values)
            text = text.Replace(value, Mask, StringComparison.Ordinal);
        return text;
    }
}

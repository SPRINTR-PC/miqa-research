using System.Text;

namespace MiresSftpUploader.Core;

/// <summary>
/// Reads a Secret value for <c>--set-secret</c>: one line from stdin when it is redirected, otherwise a prompt with
/// echo off. The prompt goes to stderr so stdout stays clean.
/// </summary>
public static class ConsoleSecretInput
{
    public static string? Read()
    {
        if (Console.IsInputRedirected) return Console.In.ReadLine();

        Console.Error.Write("Secret value (not shown): ");
        var value = new StringBuilder();
        while (true)
        {
            var key = Console.ReadKey(intercept: true);
            if (key.Key == ConsoleKey.Enter) break;
            if (key.Key == ConsoleKey.Backspace) { if (value.Length > 0) value.Length--; }
            else if (!char.IsControl(key.KeyChar)) value.Append(key.KeyChar);
        }
        Console.Error.WriteLine();
        return value.ToString();
    }
}

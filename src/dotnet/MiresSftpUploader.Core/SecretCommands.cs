using System.Text.RegularExpressions;

namespace MiresSftpUploader.Core;

/// <summary>
/// <c>--set-secret</c>, <c>--clear-secret</c> and <c>--list-secrets</c>: manage the account's Secret Store without a window.
/// The value is never taken from the command line, where it would show in process listings and shell history.
/// </summary>
internal static partial class SecretCommands
{
    public static int Run(CliOptions options, ConfigurationLocations locations, Func<string?> readSecret, TextWriter stdout, TextWriter stderr)
    {
        if (locations.SecretStorePath is null || locations.Identity is null)
        {
            stderr.WriteLine("The Secret Store is not configured.");
            return ExitCodes.ConfigurationError;
        }

        var name = options.SetSecret ?? options.ClearSecret;
        if (name is not null && !ValidName().IsMatch(name))
        {
            stderr.WriteLine($"Unknown Secret name. Use sftp-password, sftp-key-passphrase, s3-access-key:<Source> or s3-secret-key:<Source>.");
            return ExitCodes.ConfigurationError;
        }

        try
        {
            using var store = SecretStore.Open(locations.SecretStorePath, locations.Identity);
            if (options.ListSecrets)
            {
                foreach (var secret in store.List())
                    stdout.WriteLine($"{secret.Name}\t{secret.State.ToString().ToLowerInvariant()}");
                return ExitCodes.Ok;
            }

            if (options.ClearSecret is not null)
            {
                store.Clear(options.ClearSecret);
                stdout.WriteLine($"Cleared {options.ClearSecret}.");
                return ExitCodes.Ok;
            }

            var value = readSecret();
            if (string.IsNullOrEmpty(value))
            {
                stderr.WriteLine("No value was given; nothing was stored.");
                return ExitCodes.ConfigurationError;
            }

            store.Set(options.SetSecret!, value);
            stdout.WriteLine($"Stored {options.SetSecret}.");
            return ExitCodes.Ok;
        }
        catch (SecretStoreUnavailableException e)
        {
            stderr.WriteLine(e.Message);
            return ExitCodes.ConfigurationError;
        }
    }

    [GeneratedRegex(@"^(sftp-password|sftp-key-passphrase|s3-(access|secret)-key:.+)$", RegexOptions.CultureInvariant)]
    private static partial Regex ValidName();
}

using System.Collections;
using Microsoft.Extensions.Configuration;

namespace Miqa.Infrastructure.Configuration;

public class EnvironmentVariables
{
    private static readonly IEnumerable<string> CommaSeparatedSettingsListValue = new[]
    {
        "AllowedIPAddresses".ToLower()
    };
    
    public static IConfiguration ReplaceConfigurationValuesIfMiqaEnvironmentVariablesExist(IConfiguration configuration)
    {
        var allEnvVars = GetMiqaEnvironmentVariables();

        foreach (var envVar in allEnvVars)
        {
            var key = envVar.Key.ToString();
            if (key is null) continue;
            
            var keyWithoutLeadingMires = key.ToLower().Replace("mires_", "");
            var keyWithColonsInsteadOfUnderscored = keyWithoutLeadingMires.Replace("__", ":");
            keyWithColonsInsteadOfUnderscored = keyWithColonsInsteadOfUnderscored.Replace("_", ":");
            
            configuration[keyWithColonsInsteadOfUnderscored] = envVar.Value?.ToString();
        }
        
        return configuration;
    }

    private static IEnumerable<DictionaryEntry> GetMiqaEnvironmentVariables()
    {
        var allEnvVars = Environment.GetEnvironmentVariables();
        foreach (var envVar in allEnvVars.Cast<DictionaryEntry>()
                     .Where(envVar => (envVar.Key.ToString() ?? "").ToLower().StartsWith("mires_")))
        {
            yield return envVar;
        }
    }

    private static IEnumerable<string> GetListFromCommaSeparatedString(string commaSeparatedString)
    {
        var values = commaSeparatedString.Split(",", StringSplitOptions.RemoveEmptyEntries).ToList();

        foreach (var value in values)
        {
            yield return value.Trim();
        }
    }
}
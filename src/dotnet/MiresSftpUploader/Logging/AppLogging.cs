using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;
using MiresSftpUploader.Core;
using NLog;
using NLog.Config;
using NLog.Extensions.Logging;
using NLog.Targets;
using NLog.Targets.Wrappers;

namespace MiresSftpUploader.Logging;

/// <summary>
/// Sets up NLog for a Run. With an <c>NLog</c> section in the configuration, that section is the whole NLog
/// configuration; without one, a configuration is generated from the <c>Logging</c> settings: a daily-archived
/// file with the configured retention, stderr in a Headless Run, and the log pane in the UI. Every message passes
/// the <see cref="Redactor"/> before NLog sees it.
/// </summary>
public sealed class AppLogging : IDisposable
{
    public const string FileName = "uploader.log";
    private const string Layout = "${longdate}|${level:uppercase=true}|${logger}|${message}";

    private readonly ILoggerFactory _loggerFactory;

    private AppLogging(LogFactory logFactory, ILoggerFactory loggerFactory, UiLogTarget? ui, string directory)
    {
        LogFactory = logFactory;
        _loggerFactory = loggerFactory;
        Ui = ui;
        Directory = directory;
    }

    public LogFactory LogFactory { get; }
    public ILoggerFactory LoggerFactory => _loggerFactory;

    /// <summary>The target feeding the log pane; null in a Headless Run.</summary>
    public UiLogTarget? Ui { get; }

    /// <summary>The directory the generated configuration writes to.</summary>
    public string Directory { get; }

    /// <param name="nlogSection">The effective flat keys under <c>NLog</c> (<see cref="LoadResult.Section"/>); empty means generate.</param>
    /// <param name="defaultDirectory">Used when <c>Logging:Directory</c> is not set.</param>
    /// <param name="fileOnly">Only the file target, for the Settings TUI: the console belongs to the interface and stdout must stay empty.</param>
    public static AppLogging Start(LoggingConfig config, IReadOnlyDictionary<string, string> nlogSection, bool headless, Redactor redactor, string defaultDirectory, bool fileOnly = false)
    {
        var directory = string.IsNullOrWhiteSpace(config.Directory) ? defaultDirectory : config.Directory;
        var logFactory = new LogFactory();
        logFactory.Setup().SetupExtensions(e => e.RegisterTarget<UiLogTarget>());

        if (nlogSection.Count > 0)
        {
            var root = new ConfigurationBuilder()
                .AddInMemoryCollection(nlogSection.Select(kv => new KeyValuePair<string, string?>("NLog:" + kv.Key, kv.Value)))
                .Build();
            logFactory.Setup().LoadConfigurationFromSection(root);
            if (fileOnly && logFactory.Configuration is { } loaded)
            {
                RemoveTerminalTargets(loaded);
                logFactory.Configuration = loaded;
            }
        }
        else
        {
            logFactory.Configuration = Generate(config, directory, headless, fileOnly);
        }

        var ui = logFactory.Configuration?.AllTargets.OfType<UiLogTarget>().FirstOrDefault();
        var provider = new RedactingLoggerProvider(new NLogLoggerProvider(new NLogProviderOptions(), logFactory), redactor);
        var loggerFactory = Microsoft.Extensions.Logging.LoggerFactory.Create(b => b.SetMinimumLevel(Microsoft.Extensions.Logging.LogLevel.Trace).AddProvider(provider));
        return new AppLogging(logFactory, loggerFactory, ui, directory);
    }

    /// <summary>Takes the console and log-pane targets (also behind a wrapper) out of a user-supplied configuration: the Settings TUI owns the terminal.</summary>
    private static void RemoveTerminalTargets(LoggingConfiguration configuration)
    {
        static bool IsTerminal(Target? t) => t switch
        {
            ConsoleTarget or ColoredConsoleTarget or UiLogTarget => true,
            WrapperTargetBase w => IsTerminal(w.WrappedTarget),
            _ => false,
        };

        foreach (var rule in configuration.LoggingRules.ToList())
        {
            foreach (var t in rule.Targets.Where(IsTerminal).ToList()) rule.Targets.Remove(t);
            if (rule.Targets.Count == 0) configuration.LoggingRules.Remove(rule);
        }

        foreach (var t in configuration.AllTargets.Where(IsTerminal).ToList()) configuration.RemoveTarget(t.Name);
    }

    private static LoggingConfiguration Generate(LoggingConfig config, string directory, bool headless, bool fileOnly)
    {
        var minimum = ToNLog(config.Level);
        var configuration = new LoggingConfiguration();

        var file = new FileTarget("file")
        {
            FileName = Path.Combine(directory, FileName),
            Layout = Layout,
            ArchiveEvery = FileArchivePeriod.Day,
            MaxArchiveDays = config.RetainDays,
        };
        // The 10 s progress lines of a Headless Run go to the log file only: a first, final rule keeps them from the console rule below.
        if (headless) configuration.LoggingRules.Add(new LoggingRule(HeadlessProgress.LoggerName, minimum, NLog.LogLevel.Fatal, file) { Final = true });
        configuration.AddRule(minimum, NLog.LogLevel.Fatal, file);

        if (!fileOnly && (config.Console ?? headless))
        {
            var console = new ConsoleTarget("console") { StdErr = true, Layout = Layout };
            configuration.AddRule(minimum, NLog.LogLevel.Fatal, console);
        }

        if (!headless && !fileOnly)
        {
            // The pane has its own level filter, so it sees Debug even when the file is at Info.
            var ui = new UiLogTarget { Name = "ui" };
            configuration.AddRule(minimum.Ordinal < NLog.LogLevel.Debug.Ordinal ? minimum : NLog.LogLevel.Debug, NLog.LogLevel.Fatal, ui);
        }

        return configuration;
    }

    private static NLog.LogLevel ToNLog(LogLevelSetting level) => level switch
    {
        LogLevelSetting.Trace => NLog.LogLevel.Trace,
        LogLevelSetting.Debug => NLog.LogLevel.Debug,
        LogLevelSetting.Info => NLog.LogLevel.Info,
        LogLevelSetting.Warn => NLog.LogLevel.Warn,
        LogLevelSetting.Error => NLog.LogLevel.Error,
        _ => NLog.LogLevel.Fatal,
    };

    /// <summary>Flushes and closes every target. Call before the process returns, so the last lines are not lost.</summary>
    public void Dispose()
    {
        _loggerFactory.Dispose();
        LogFactory.Shutdown();
    }
}

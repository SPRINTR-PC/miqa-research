using Microsoft.Data.Sqlite;
using Microsoft.Extensions.Logging.Abstractions;
using MiresSftpUploader.Core;
using MiresSftpUploader.Test.Support;

// Commands (each prints one line and exits non-zero on failure):
//   init <dataDir>              the real --init-data-dir
//   run <dataDir> <fileName>    a Run uploading one fake file, so the Upload State is written
//   hold <dataDir> <readyFile> <stopFile>   keeps a connection open (so -wal and -shm exist) until stopFile appears
//   count <dataDir>             prints the number of Runs recorded
var command = args.Length > 0 ? args[0] : "";
var dataDir = args.Length > 1 ? args[1] : "";
var database = DataDirectory.DatabasePath(dataDir);

switch (command)
{
    case "init":
        Cli.TryRun(["--init-data-dir", "--data-dir", dataDir], "probe", Console.Out, Console.Error, out var initExit);
        return initExit;

    case "run":
    {
        var settings = new EngineSettings { Destination = "sftp.example:22", State = new StateSettings { Path = database } };
        var source = new FakeSource("scans").Add(args[2], "content of " + args[2]);
        var engine = new Engine(new FakeRemote(), [source], settings, NullLogger<Engine>.Instance, TimeProvider.System);
        var result = await engine.RunAsync(new RunOptions(), new Progress<RunEvent>(), CancellationToken.None);
        Console.WriteLine($"run exit={result.ExitCode} {result.Reason}");
        return result.ExitCode;
    }

    case "hold":
    {
        using var connection = Open(database);
        Scalar(connection, "SELECT count(*) FROM Runs");
        File.WriteAllText(args[2], "ready");
        while (!File.Exists(args[3])) await Task.Delay(50);
        Console.WriteLine("hold done");
        return 0;
    }

    case "count":
    {
        using var connection = Open(database);
        Console.WriteLine($"runs={Scalar(connection, "SELECT count(*) FROM Runs")}");
        return 0;
    }

    default:
        Console.Error.WriteLine("unknown command");
        return 64;
}

static SqliteConnection Open(string path)
{
    var connection = new SqliteConnection($"Data Source={path};Mode=ReadWrite;Pooling=False");
    connection.Open();
    return connection;
}

static object? Scalar(SqliteConnection connection, string sql)
{
    using var command = connection.CreateCommand();
    command.CommandText = sql;
    return command.ExecuteScalar();
}

using System.Diagnostics;

namespace MiresSftpUploader.Test.Integration;

/// <summary>
/// Two OS accounts in one group share the Upload State, the way the Linux Data Directory is meant to work.
/// Runs the probe program (tests/dotnet/MiresSftpUploader.Test.ContainerProbe) under uids 1001 and 1002 in a
/// mcr.microsoft.com/dotnet/runtime container with a 022 umask, so group access can only come from the app's own modes and the setgid directory.
/// Needs a Docker-compatible CLI; excluded from the default run by its Container category.
/// </summary>
[TestClass]
public sealed class SharedDataDirectoryContainerTests
{
    private const string Image = "mcr.microsoft.com/dotnet/runtime:10.0";

    // setpriv --init-groups gives the uid its supplementary groups (mires-uploader), as a login would.
    private const string Script = """
        set -eu
        umask 022
        groupadd -g 2000 mires-uploader
        useradd -M -u 1001 -G mires-uploader u1
        useradd -M -u 1002 -G mires-uploader u2
        export DOTNET_EnableDiagnostics=0 DOTNET_CLI_TELEMETRY_OPTOUT=1 HOME=/tmp
        probe="dotnet /app/MiresSftpUploader.Test.ContainerProbe.dll"
        as() { u=$1; shift; setpriv --reuid="$u" --regid="$u" --init-groups $probe "$@"; }

        $probe init /srv/mires
        echo "dir=$(stat -c '%a %G' /srv/mires)"

        as 1001 run /srv/mires first.txt
        echo "after-u1 db=$(stat -c '%a %G' /srv/mires/upload-state.db) lock=$(stat -c '%a %G' /srv/mires/upload-state.db.lock)"

        # u1 keeps a connection open so -wal and -shm exist; u2 writes and reads while they do.
        as 1001 hold /srv/mires /tmp/ready /tmp/stop &
        holder=$!
        for i in $(seq 1 200); do [ -f /tmp/ready ] && break; sleep 0.1; done
        echo "wal=$(stat -c '%a %G' /srv/mires/upload-state.db-wal) shm=$(stat -c '%a %G' /srv/mires/upload-state.db-shm)"
        as 1002 run /srv/mires second.txt
        as 1002 count /srv/mires
        touch /tmp/stop
        wait $holder

        # Then in turn again, after the -wal has been removed and is created afresh.
        as 1002 run /srv/mires third.txt
        as 1001 run /srv/mires fourth.txt
        as 1001 count /srv/mires
        echo DONE
        """;

    [TestMethod]
    [TestCategory("Container")]
    public void Two_uids_in_one_group_create_write_and_read_the_database_in_turn_including_after_wal_creation()
    {
        var app = AppContext.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar);
        var start = new ProcessStartInfo("docker")
        {
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            UseShellExecute = false,
        };
        foreach (var arg in new[] { "run", "--rm", "-v", $"{app}:/app:ro", "--entrypoint", "bash", Image, "-c", Script })
            start.ArgumentList.Add(arg);

        using var process = Process.Start(start)!;
        var stdout = process.StandardOutput.ReadToEndAsync();
        var stderr = process.StandardError.ReadToEndAsync();
        Assert.IsTrue(process.WaitForExit(TimeSpan.FromMinutes(5)), "container run timed out");
        var output = stdout.Result;

        Assert.AreEqual(0, process.ExitCode, $"stdout:\n{output}\nstderr:\n{stderr.Result}");
        StringAssert.Contains(output, "dir=2770 mires-uploader");
        StringAssert.Contains(output, "db=660 mires-uploader");
        StringAssert.Contains(output, "wal=660 mires-uploader shm=660 mires-uploader");
        StringAssert.Contains(output, "runs=4");
        StringAssert.Contains(output, "DONE");
    }
}

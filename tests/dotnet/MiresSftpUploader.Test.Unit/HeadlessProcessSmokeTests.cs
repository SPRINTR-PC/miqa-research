using MiresSftpUploader.Test.Support;
using System.Diagnostics;

namespace MiresSftpUploader.Test.Unit;

/// <summary>Starts the real executable with --headless: it must run the Engine, print one summary line and exit, with no window.</summary>
[TestClass]
public sealed class HeadlessProcessSmokeTests
{
    private static (int Exit, string Out, string Err) Start(Dictionary<string, string> env, params string[] args)
    {
        var info = new ProcessStartInfo("dotnet") { RedirectStandardOutput = true, RedirectStandardError = true };
        info.ArgumentList.Add(typeof(AppHost).Assembly.Location);
        foreach (var a in args) info.ArgumentList.Add(a);
        foreach (var (k, v) in env) info.Environment[k] = v;
        info.Environment.Remove("DISPLAY");
        using var process = Process.Start(info)!;
        var stdout = process.StandardOutput.ReadToEndAsync();
        var stderr = process.StandardError.ReadToEndAsync();
        Assert.IsTrue(process.WaitForExit(60_000), "the headless run did not finish");
        return (process.ExitCode, stdout.Result, stderr.Result);
    }

    [TestMethod]
    public void Headless_runs_the_Engine_and_prints_only_the_summary_line()
    {
        var dir = Directory.CreateTempSubdirectory("mires-smoke-").FullName;
        try
        {
            var source = Directory.CreateDirectory(Path.Combine(dir, "src")).FullName;
            File.WriteAllText(Path.Combine(source, "a.txt"), "alpha");
            var env = new Dictionary<string, string>
            {
                ["MIRES_DATA_DIR"] = Path.Combine(dir, "data"),
                ["MIRES_State__AccessGroup"] = TestAccessGroup.Name ?? "",
                ["MIRES_Sftp__Host"] = "127.0.0.1",
                ["MIRES_Sftp__Port"] = "1",
                ["MIRES_Sftp__Username"] = "u",
                ["MIRES_Sftp__HostKeyFingerprint"] = "abc",
                ["MIRES_Sources__0__Name"] = "alpha",
                ["MIRES_Sources__0__Path"] = source,
                ["MIRES_Logging__Directory"] = Path.Combine(dir, "logs"),
            };

            var r = Start(env, "--headless");

            Assert.AreEqual(3, r.Exit, r.Err);
            Assert.AreEqual(1, r.Out.TrimEnd().Split('\n').Length, r.Out);
            StringAssert.StartsWith(r.Out, "succeeded=0 skipped=0 failed=");
            StringAssert.Contains(r.Out, "exit=3");
        }
        finally
        {
            try { Directory.Delete(dir, true); } catch (IOException) { }
        }
    }
}

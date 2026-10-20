using System.Text;

namespace MiresSftpUploader.Core;

/// <summary>
/// The single-instance lock beside the Upload State. The operating system holds the lock on an open file
/// (FileShare.None), so a process that died never leaves it held: a stale file is simply opened again.
/// The file also names the holder (PID, user, start time) so a refusal can say who has the lock
/// (readable on Unix; Windows denies reading a file opened with FileShare.None, so the holder is then unknown).
/// </summary>
internal sealed class RunLock : IDisposable
{
    private readonly FileStream _stream;

    private RunLock(FileStream stream) => _stream = stream;

    /// <summary>Returns the lock, or null with <paramref name="holder"/> describing the current holder when another Run has it.</summary>
    public static RunLock? TryAcquire(string path, string startedBy, DateTimeOffset now, out string holder)
    {
        var directory = Path.GetDirectoryName(Path.GetFullPath(path));
        if (!string.IsNullOrEmpty(directory)) Directory.CreateDirectory(directory);

        FileStream stream;
        try
        {
            stream = new FileStream(path, FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None);
        }
        catch (IOException)
        {
            holder = DescribeHolder(path);
            return null;
        }

        stream.SetLength(0);
        stream.Write(Encoding.UTF8.GetBytes($"pid={Environment.ProcessId} user={startedBy} since={now:O}"));
        stream.Flush();
        holder = "";
        return new RunLock(stream);
    }

    private static string DescribeHolder(string path)
    {
        try
        {
            using var reader = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);
            using var text = new StreamReader(reader, Encoding.UTF8);
            var content = text.ReadToEnd().Trim();
            return content.Length > 0 ? content : "unknown holder";
        }
        catch (IOException)
        {
            return "unknown holder";
        }
    }

    public void Dispose() => _stream.Dispose();
}

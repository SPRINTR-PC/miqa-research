namespace MiresSftpUploader.Core;

/// <summary>The status of one file in a Run.</summary>
public enum FileOutcome
{
    Pending,
    Hashing,
    Uploading,
    Verifying,
    Succeeded,
    Failed,
    Skipped,
    Ignored,
}

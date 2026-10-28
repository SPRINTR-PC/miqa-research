namespace MiresSftpUploader.Tui;

/// <summary>The TUI-only Help topic "Keys": the global keys and each page's keys. Keep it in step with the pages' key hints.</summary>
public static class KeysTopic
{
    public const string Markdown = """
        # Keys

        ## Everywhere

        - F9 Upload, F10 History, F11 Settings, F12 Help (or click the tab).
        - Ctrl+Q (or Ctrl+C) quits. During a Run it asks whether to cancel the Run and quit, or go back. With unsaved Settings it asks Save, Discard or Cancel.
        - Tab moves between the parts of a page. Enter activates the focused item. The mouse works where the terminal supports it and is never required.

        ## Upload

        - R Run, D Dry run, S Scan, X Cancel the Run, T Retry failed files.
        - 1-4 filter the file table (succeeded, failed, skipped, pending).
        - Space includes or excludes the selected Source.
        - L shows or hides the Log pane.
        - End follows the active file; moving the cursor stops following.

        ## History

        - 1-3 filter the Runs (All, Attention, Live).
        - F Failed only (outcomes of the selected Run).
        - R Retry the failed files of the selected Run (opens Upload).
        - X Cancel the selected Run (Request cancel for another user's Run).
        - J / C export a Report as JSON or CSV.
        - F5 refresh.

        ## Settings

        - Up/Down choose a page, Right or Enter edit it, Esc go back.
        - Ctrl+S Save, Ctrl+R Revert, F4 Issues, F5 Check connection.
        - Ctrl+PgUp / Ctrl+PgDn previous or next page.

        ## Help

        - Up/Down choose a topic or scroll. PgUp, PgDn, Home and End scroll.
        - Tab switches between the topic list and the text.
        """;
}

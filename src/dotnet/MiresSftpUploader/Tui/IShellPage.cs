using Terminal.Gui.Input;

namespace MiresSftpUploader.Tui;

public enum ShellTab { Upload, History, Settings, Help }

/// <summary>A page of the whole-app TUI other than Settings: the text the shell shows for it and the keys the shell routes to it.</summary>
public interface IShellPage
{
    /// <summary>The page's text in the shell's shared status line.</summary>
    string StatusText { get; }

    /// <summary>The page's keys in the shell's shared key bar; must fit the 80-column bar together with the shell's own keys.</summary>
    string KeyHints { get; }

    /// <summary>Handles a page key (letters, digits) before any view sees it; true when it was used. Only called while this page is shown.</summary>
    bool HandleKey(Key key);

    /// <summary>Puts the focus where the user left off (or on the page's first control); called after every switch to the page.</summary>
    void FocusDefault();
}

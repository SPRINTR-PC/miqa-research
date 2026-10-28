using Terminal.Gui.Input;
using Terminal.Gui.ViewBase;
using Terminal.Gui.Views;

namespace MiresSftpUploader.Tui;

/// <summary>A page whose real content a later ticket adds (Upload, History, Help). Focusable so the shell can always put the focus on it.</summary>
public sealed class PlaceholderPage : View, IShellPage
{
    public PlaceholderPage(string title)
    {
        CanFocus = true;
        Add(new Label
        {
            X = Pos.Center(), Y = Pos.Center(), Text = title + ": not available yet in the terminal interface.",
            HotKeySpecifier = new System.Text.Rune('￿'),
        });
    }

    public string StatusText => "";

    public string KeyHints => "";

    public event System.Action? ChromeChanged { add { } remove { } }

    public bool HandleKey(Key key) => false;

    public void FocusDefault() => SetFocus();
}

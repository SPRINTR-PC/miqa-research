using Terminal.Gui.Drawing;
using Terminal.Gui.ViewBase;
using Attr = Terminal.Gui.Drawing.Attribute;

namespace MiresSftpUploader.SettingsTui;

/// <summary>One palette, applied per view. Colours carry meaning: cyan = navigation, green = changed, red = error, amber = locked or warning, grey = help.</summary>
public static class Theme
{
    static Color C(int r, int g, int b) => new(r, g, b);

    public static readonly Color Bg = C(22, 24, 38), Panel = C(30, 33, 52), Raised = C(44, 49, 78), Input = C(14, 16, 28),
        Text = C(205, 214, 244), Dim = C(120, 128, 160), Accent = C(122, 162, 247), Cyan = C(86, 212, 221),
        Green = C(158, 206, 106), Red = C(247, 118, 142), Amber = C(224, 175, 104), Violet = C(187, 154, 247);

    static Attr A(Color fg, Color bg) => new(fg, bg);

    static Scheme Make(Color bg, Color fg, Color hot, Color focusBg, Color focusFg) => new()
    {
        Normal = A(fg, bg),
        HotNormal = A(hot, bg),
        Focus = A(focusFg, focusBg),
        HotFocus = A(hot, focusBg),
        Active = A(focusFg, focusBg),
        HotActive = A(hot, focusBg),
        Highlight = A(Text, Raised),
        Editable = A(Text, Input),
        ReadOnly = A(Dim, Panel),
        Disabled = A(Dim, bg),
    };

    /// <summary>Window and rows.</summary>
    public static readonly Scheme Base = Make(Bg, Text, Cyan, Accent, Bg);
    /// <summary>Sidebar and form frames.</summary>
    public static readonly Scheme Pane = Make(Panel, Text, Cyan, Accent, Bg);
    public static readonly Scheme Nav = Make(Panel, Cyan, Amber, Accent, Bg);
    public static readonly Scheme Header = Make(Raised, Violet, Violet, Raised, Violet);
    public static readonly Scheme Bar = Make(Raised, Text, Amber, Raised, Text);
    public static readonly Scheme Error = Make(Panel, Red, Red, Panel, Red);
    public static readonly Scheme Locked = Make(Panel, Amber, Amber, Panel, Amber);
    public static readonly Scheme Help = Make(Panel, Dim, Dim, Panel, Dim);
    public static readonly Scheme Changed = Make(Panel, Green, Green, Panel, Green);
    public static readonly Scheme Ok = Make(Raised, Green, Green, Raised, Green);

    public static T Apply<T>(this T v, Scheme s) where T : View { v.SetScheme(s); return v; }
}

using MiresSftpUploader.SettingsTui;
using Terminal.Gui.App;
using Terminal.Gui.Drivers;
using Terminal.Gui.Input;
using Terminal.Gui.Testing;

namespace MiresSftpUploader.Test.Unit;

/// <summary>The real Confirm dialog, driven headlessly: a timer injects the key while the modal runs.</summary>
[TestClass]
public class SettingsTuiConfirmDialogTests
{
    private static bool Ask(params Key[] keys)
    {
        using var app = Application.Create();
        app.Init(DriverRegistry.Names.ANSI);
        app.Driver!.SetScreenSize(100, 32);
        var pending = new Queue<Key>(keys);
        app.AddTimeout(TimeSpan.FromMilliseconds(100), () =>
        {
            if (pending.Count == 0) return false;
            app.InjectKey(pending.Dequeue());
            return pending.Count > 0;
        });
        return new TerminalGuiDialogs(app).Confirm("Change?", "Really change it?");
    }

    [TestMethod, Timeout(20000)]
    public void Enter_takes_the_default_button_which_is_Cancel() => Assert.IsFalse(Ask(Key.Enter));

    [TestMethod, Timeout(20000)]
    public void Esc_cancels() => Assert.IsFalse(Ask(Key.Esc));

    [TestMethod, Timeout(20000)]
    public void Choosing_the_other_button_confirms() => Assert.IsTrue(Ask(Key.CursorLeft, Key.Enter));
}

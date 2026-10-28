using System.Drawing;
using Terminal.Gui.App;
using Terminal.Gui.Drivers;
using Terminal.Gui.Input;
using Terminal.Gui.Testing;
using Terminal.Gui.Views;

namespace MiresSftpUploader.Test.Support;

/// <summary>
/// A TUI under the real <c>Application.Run</c> loop on its own thread (ANSI driver, headless). Tests drive it the way a user does:
/// <see cref="Press(Key, bool)"/>, <see cref="Click"/>, <see cref="Resize"/>, then <see cref="WaitUntil"/> something shows on the <see cref="Screen"/>.
/// Everything that touches a view runs on the UI thread through <see cref="OnUi(Action, bool)"/>; there are no sleeps, only polling with a deadline.
/// </summary>
public sealed class TuiTestHost : IDisposable
{
    private static readonly TimeSpan DefaultTimeout = TimeSpan.FromSeconds(10);

    private readonly Thread _thread;
    private readonly ManualResetEventSlim _ready = new();
    private Exception? _failure;
    private IApplication? _app;
    private Window? _root;

    /// <param name="create">Builds the root window on the UI thread, after the application was initialised.</param>
    public TuiTestHost(Func<IApplication, Window> create, int width = 100, int height = 32)
    {
        _thread = new Thread(() =>
        {
            try
            {
                var app = Application.Create();
                _app = app;
                app.Init(DriverRegistry.Names.ANSI);
                app.Driver!.SetScreenSize(width, height);
                _root = create(app);
                app.Iteration += (_, _) => _ready.Set();
                app.Run(_root);
                _root.Dispose();
                app.Dispose();
            }
            catch (Exception e)
            {
                _failure = e;
            }
            finally
            {
                _ready.Set();
                Stopped.Set();
            }
        }) { Name = "tui-test-host", IsBackground = true };
        _thread.Start();
        Assert.IsTrue(_ready.Wait(DefaultTimeout), "the TUI did not start");
        if (_failure is not null) throw new InvalidOperationException("the TUI failed to start", _failure);
        // One more round trip: the loop is running and the first frame was laid out.
        OnUi(() => App.LayoutAndDraw(true));
    }

    public IApplication App => _app!;

    public Window Root => _root!;

    /// <summary>Set once the loop has ended (the application stopped by itself or by <see cref="Dispose"/>).</summary>
    public ManualResetEventSlim Stopped { get; } = new();

    /// <summary>Runs <paramref name="action"/> on the UI thread and waits for it. With <paramref name="mayBlock"/> (a modal opens inside it) the wait is brief.</summary>
    public void OnUi(Action action, bool mayBlock = false)
    {
        using var done = new ManualResetEventSlim();
        Exception? error = null;
        RunOnUi(() =>
        {
            try { action(); }
            catch (Exception e) { error = e; }
            finally { done.Set(); }
        });
        if (!done.Wait(mayBlock ? TimeSpan.FromMilliseconds(400) : DefaultTimeout) && !mayBlock) Assert.Fail("the UI thread did not respond");
        if (error is not null) throw new InvalidOperationException("action on the UI thread failed", error);
    }

    // A modal loop does not run Invoke callbacks but does run timeouts, so work meant to reach a modal goes through a timeout.
    private void RunOnUi(Action action) => App.AddTimeout(TimeSpan.FromMilliseconds(1), () =>
    {
        action();
        return false;
    });

    public T OnUi<T>(Func<T> read)
    {
        T result = default!;
        OnUi((Action)(() => { result = read(); }));
        return result;
    }

    /// <summary>Starts a modal on the UI thread without waiting for it to close (through <c>Invoke</c>: the callback then runs outside the timer lock that a modal opened from a timeout would hold).</summary>
    public void Post(Action action) => _ = Task.Run(() => App.Invoke(action));

    /// <summary>Types a key. A key that opens a modal (Quit asking a question) does not block the caller.</summary>
    public void Press(Key key, bool opensModal = false) => OnUi(() =>
    {
        App.InjectKey(key);
        App.LayoutAndDraw(true);
    }, opensModal);

    public void Type(string text)
    {
        foreach (var c in text) Press((Key)c);
    }

    /// <summary>A left click at a screen cell.</summary>
    public void Click(int x, int y) => OnUi(() =>
    {
        foreach (var flag in new[] { MouseFlags.LeftButtonPressed, MouseFlags.LeftButtonReleased, MouseFlags.LeftButtonClicked })
            App.Mouse.RaiseMouseEvent(new Mouse { ScreenPosition = new Point(x, y), Flags = flag });
        App.LayoutAndDraw(true);
    });

    public void Resize(int width, int height) => OnUi(() =>
    {
        App.Driver!.SetScreenSize(width, height);
        App.LayoutAndDraw(true);
    });

    public string Screen => OnUi(() =>
    {
        App.LayoutAndDraw(true);
        return App.Driver!.ToString() ?? "";
    });

    public string[] Lines => Screen.TrimEnd('\n').Split('\n');

    public bool Shows(string text) => Screen.Contains(text, StringComparison.Ordinal);

    /// <summary>The focused view's type and its ancestors, e.g. <c>TableView &lt; UploadProbe &lt; View</c>.</summary>
    public string FocusPath => OnUi(() =>
    {
        var path = new List<string>();
        for (var v = App.Navigation?.GetFocused(); v is not null; v = v.SuperView) path.Add(v.GetType().Name);
        return string.Join(" < ", path);
    });

    /// <summary>Polls until <paramref name="condition"/> (evaluated on the UI thread) holds; fails with the screen otherwise.</summary>
    public void WaitUntil(Func<bool> condition, string what, TimeSpan? timeout = null)
    {
        var deadline = DateTime.UtcNow + (timeout ?? DefaultTimeout);
        while (!OnUi(condition))
        {
            if (DateTime.UtcNow > deadline) Assert.Fail($"timed out waiting for: {what}\n{Screen}");
            Thread.Sleep(5);
        }
    }

    public void WaitUntilShows(string text) => WaitUntil(() =>
    {
        App.LayoutAndDraw(true);
        return App.Driver!.ToString()!.Contains(text, StringComparison.Ordinal);
    }, $"screen shows '{text}'");

    public void Dispose()
    {
        if (!Stopped.IsSet)
        {
            RunOnUi(() => App.RequestStop());
            Stopped.Wait(TimeSpan.FromSeconds(5));
        }

        _thread.Join(TimeSpan.FromSeconds(5));
    }
}

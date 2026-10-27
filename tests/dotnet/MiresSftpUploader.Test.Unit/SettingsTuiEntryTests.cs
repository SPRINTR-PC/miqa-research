using MiresSftpUploader.SettingsTui;

namespace MiresSftpUploader.Test.Unit;

/// <summary>The Settings TUI refuses, before it touches the terminal, whenever a full-screen interface cannot work.</summary>
[TestClass]
public sealed class SettingsTuiEntryTests
{
    private sealed record FakeTerminal(
        bool InputRedirected = false,
        bool OutputRedirected = false,
        string? Term = "xterm-256color",
        int Width = 80,
        int Height = 24,
        bool Windows = false) : ITerminalEnvironment
    {
        public bool IsInputRedirected => InputRedirected;
        public bool IsOutputRedirected => OutputRedirected;
        public string? TermVariable => Term;
        public int? WindowWidth => Width;
        public int? WindowHeight => Height;
        public bool IsWindows => Windows;
    }

    private static (int Exit, string Out, string Err, int Started) Run(ITerminalEnvironment terminal)
    {
        var stderr = new StringWriter();
        var started = 0;
        var exit = SettingsTuiEntry.Run(terminal, stderr, () => { started++; return 0; });
        return (exit, "", stderr.ToString(), started);
    }

    [TestMethod]
    public void An_interactive_terminal_of_the_minimum_size_starts_the_TUI()
    {
        var r = Run(new FakeTerminal());

        Assert.AreEqual(0, r.Exit);
        Assert.AreEqual(1, r.Started);
        Assert.AreEqual("", r.Out);
        Assert.AreEqual("", r.Err);
    }

    [TestMethod]
    public void The_exit_code_of_the_TUI_is_returned()
    {
        var exit = SettingsTuiEntry.Run(new FakeTerminal(), new StringWriter(), () => 130);

        Assert.AreEqual(130, exit);
    }

    [TestMethod]
    public void Refuses_when_stdin_is_redirected() => AssertRefused(new FakeTerminal(InputRedirected: true), "stdin");

    [TestMethod]
    public void Refuses_when_stdout_is_redirected() => AssertRefused(new FakeTerminal(OutputRedirected: true), "stdout");

    [TestMethod]
    [DataRow("dumb")]
    [DataRow("")]
    [DataRow(null)]
    public void Refuses_on_Unix_when_TERM_is_dumb_or_unset(string? term) => AssertRefused(new FakeTerminal(Term: term), "TERM");

    [TestMethod]
    public void On_Windows_TERM_is_not_required()
    {
        var r = Run(new FakeTerminal(Term: null, Windows: true));

        Assert.AreEqual(0, r.Exit);
    }

    [TestMethod]
    public void Refuses_when_the_terminal_is_narrower_than_80_columns() => AssertRefused(new FakeTerminal(Width: 79), "80x24");

    [TestMethod]
    public void Refuses_when_the_terminal_is_lower_than_24_rows() => AssertRefused(new FakeTerminal(Height: 23), "80x24");

    [TestMethod]
    public void A_larger_terminal_is_accepted() => Assert.AreEqual(0, Run(new FakeTerminal(Width: 200, Height: 60)).Exit);

    [TestMethod]
    public void An_unknown_size_is_refused()
    {
        AssertRefused(new FakeTerminal() with { }, null, unknownSize: true);
    }

    private static void AssertRefused(ITerminalEnvironment terminal, string? mention, bool unknownSize = false)
    {
        if (unknownSize) terminal = new UnknownSize();
        var r = Run(terminal);

        Assert.AreEqual(2, r.Exit);
        Assert.AreEqual(0, r.Started, "the TUI must not start");
        Assert.AreEqual("", r.Out);
        Assert.AreEqual(1, r.Err.TrimEnd().Split('\n').Length, r.Err);
        if (mention is not null) StringAssert.Contains(r.Err, mention);
    }

    private sealed class UnknownSize : ITerminalEnvironment
    {
        public bool IsInputRedirected => false;
        public bool IsOutputRedirected => false;
        public string? TermVariable => "xterm";
        public int? WindowWidth => null;
        public int? WindowHeight => null;
        public bool IsWindows => false;
    }
}

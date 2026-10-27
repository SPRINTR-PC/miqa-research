using MiresSftpUploader.SettingsTui;

namespace MiresSftpUploader.Test.Unit;

/// <summary>Tab completion of path fields as pure functions: a real temp directory for the Unix side, a fake listing for Windows-style paths.</summary>
[TestClass]
public sealed class PathCompletionTests
{
    private string _root = "";

    [TestInitialize]
    public void MakeTree()
    {
        _root = Path.Combine(Path.GetTempPath(), "pathcompletion-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(Path.Combine(_root, "alpha"));
        Directory.CreateDirectory(Path.Combine(_root, "alpine"));
        Directory.CreateDirectory(Path.Combine(_root, "beta"));
        Directory.CreateDirectory(Path.Combine(_root, ".hidden"));
        File.WriteAllText(Path.Combine(_root, "alpaca.txt"), "");
        File.WriteAllText(Path.Combine(_root, "gamma.txt"), "");
        File.WriteAllText(Path.Combine(_root, ".dotfile"), "");
    }

    [TestCleanup]
    public void RemoveTree() => Directory.Delete(_root, true);

    private string P(string tail) => _root + "/" + tail;

    private PathCompletion.Result Complete(string input, string? home = null) =>
        PathCompletion.Complete(input, LocalListing.Instance, home, windows: false);

    [TestMethod]
    public void A_unique_directory_completes_and_gets_a_trailing_separator()
    {
        var r = Complete(P("be"));
        Assert.AreEqual(P("beta/"), r.Text);
        Assert.AreEqual(0, r.Candidates.Count);
    }

    [TestMethod]
    public void A_unique_file_completes_without_a_separator()
    {
        Assert.AreEqual(P("gamma.txt"), Complete(P("ga")).Text);
    }

    [TestMethod]
    public void Several_matches_complete_the_common_prefix_and_list_directories_first()
    {
        var r = Complete(P("al"));
        Assert.AreEqual(P("alp"), r.Text);
        CollectionAssert.AreEqual(new[] { "alpha/", "alpine/", "alpaca.txt" }, r.Candidates.ToArray());
    }

    [TestMethod]
    public void Several_matches_without_a_longer_common_prefix_still_list_them()
    {
        var r = Complete(P("alp"));
        Assert.AreEqual(P("alp"), r.Text);
        Assert.AreEqual(3, r.Candidates.Count);
        Assert.IsTrue(r.HasEffect(P("alp")));
    }

    [TestMethod]
    public void No_match_has_no_effect_so_Tab_can_move_on()
    {
        var r = Complete(P("zzz"));
        Assert.AreEqual(P("zzz"), r.Text);
        Assert.IsFalse(r.HasEffect(P("zzz")));
        Assert.IsFalse(Complete("").HasEffect(""));
    }

    [TestMethod]
    public void A_complete_file_name_has_nothing_left_to_complete()
    {
        Assert.IsFalse(Complete(P("gamma.txt")).HasEffect(P("gamma.txt")));
    }

    [TestMethod]
    public void Hidden_entries_show_only_when_the_prefix_starts_with_a_dot()
    {
        Assert.AreEqual(P("beta/"), Complete(P("b")).Text);
        Assert.IsFalse(Complete(P("")).Candidates.Any(c => c.StartsWith('.')));
        Assert.AreEqual(P(".hidden/"), Complete(P(".h")).Text);
        CollectionAssert.AreEqual(new[] { ".hidden/", ".dotfile" }, Complete(P(".")).Candidates.ToArray());
    }

    [TestMethod]
    public void A_trailing_separator_lists_the_directory()
    {
        var r = Complete(P(""));
        CollectionAssert.AreEqual(new[] { "alpha/", "alpine/", "beta/", "alpaca.txt", "gamma.txt" }, r.Candidates.ToArray());
        Assert.AreEqual(P(""), r.Text);
    }

    [TestMethod]
    public void A_directory_typed_in_full_gets_its_separator()
    {
        Assert.AreEqual(P("beta/"), Complete(P("beta")).Text);
    }

    [TestMethod]
    public void A_file_typed_in_full_is_complete_so_Tab_can_move_on()
    {
        Assert.IsFalse(Complete(P("gamma.txt")).HasEffect(P("gamma.txt")));
    }

    [TestMethod]
    public void Tilde_expands_to_the_home_directory()
    {
        Assert.AreEqual(P("beta/"), Complete("~/be", home: _root).Text);
        Assert.AreEqual(_root + "/", Complete("~", home: _root).Text);
        Assert.AreEqual("~x", Complete("~x", home: _root).Text, "only ~ and ~/ are home");
    }

    [TestMethod]
    public void Tilde_is_left_alone_on_Windows_and_without_a_home()
    {
        Assert.IsFalse(Complete("~/be", home: null).HasEffect("~/be"));
        var win = PathCompletion.Complete(@"~\be", new FakeListing(), home: @"C:\Users\me", windows: true);
        Assert.IsFalse(win.HasEffect(@"~\be"));
    }

    private sealed class FakeListing : IDirectoryListing
    {
        public Dictionary<string, PathEntry[]> Dirs { get; } = new(StringComparer.OrdinalIgnoreCase);

        public IEnumerable<PathEntry> Entries(string directory) => Dirs.TryGetValue(directory, out var e) ? e : [];
    }

    private static FakeListing WindowsDisk() => new()
    {
        Dirs =
        {
            [@"C:\"] = [new("Data", true), new("Users", true), new("Program Files", true), new("boot.ini", false)],
            [@"C:\Data\"] = [new("Staging", true), new("State", true)],
            ["D:/"] = [new("Reports", true)],
        },
    };

    [TestMethod]
    public void Windows_paths_complete_with_backslashes_and_ignore_case()
    {
        var r = PathCompletion.Complete(@"C:\us", WindowsDisk(), null, windows: true);
        Assert.AreEqual(@"C:\Users\", r.Text);
    }

    [TestMethod]
    public void Windows_ambiguous_completion_uses_the_common_prefix_and_lists_candidates()
    {
        var r = PathCompletion.Complete(@"C:\Data\S", WindowsDisk(), null, windows: true);
        Assert.AreEqual(@"C:\Data\Sta", r.Text);
        CollectionAssert.AreEqual(new[] { @"Staging\", @"State\" }, r.Candidates.ToArray());
    }

    [TestMethod]
    public void Windows_keeps_the_separator_style_the_user_typed()
    {
        Assert.AreEqual("D:/Reports/", PathCompletion.Complete("D:/R", WindowsDisk(), null, windows: true).Text);
        Assert.AreEqual(@"C:\Data\", PathCompletion.Complete(@"C:\da", WindowsDisk(), null, windows: true).Text);
    }

    [TestMethod]
    public void Windows_names_with_spaces_complete()
    {
        Assert.AreEqual(@"C:\Program Files\", PathCompletion.Complete(@"C:\Prog", WindowsDisk(), null, windows: true).Text);
    }
}

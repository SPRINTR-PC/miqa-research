using MiresSftpUploader.Core;
using MiresSftpUploader.SettingsTui;
using Terminal.Gui.Input;
using Terminal.Gui.ViewBase;
using Terminal.Gui.Views;

namespace MiresSftpUploader.Test.Unit;

/// <summary>The Secrets page and the S3 key rows of a Source form: masked field, Save, Clear, status; all against a temp Secret Store.</summary>
[TestClass]
public sealed class SettingsTuiSecretsTests : SettingsTuiTestBase
{
    private const string Value = "hunter2-very-secret";

    private sealed record FixedIdentity(string? MachineId, string Account) : IMachineIdentity;

    private static readonly FixedIdentity Alice = new("machine-1", "alice");

    private string StorePath => Path.Combine(Dir, "user", "secrets.db");

    private Configuration CreateWithStore(Dictionary<string, string?>? env = null, IMachineIdentity? identity = null, bool withS3 = false)
    {
        var machine = ValidMachine();
        if (withS3)
            machine["Sources"]!.AsArray().Add(System.Text.Json.Nodes.JsonNode.Parse("""{ "Name": "wsi", "Type": "S3", "Endpoint": "https://s3.example.org", "Bucket": "b" }"""));
        File.WriteAllText(MachinePath, machine.ToJsonString());
        return new(new ConfigurationLocations(MachinePath, UserPath, env ?? [], StorePath, identity ?? Alice));
    }

    private SettingsTuiHarness OpenPage(string title, Configuration cfg)
    {
        var tui = Start(cfg);
        tui.Window.PageIndex = PageCatalog.Titles.ToList().IndexOf(title);
        tui.Draw();
        return tui;
    }

    /// <summary>The status under the Secret row labelled <paramref name="label"/> (the text left of the Save button), as drawn.</summary>
    private static string StatusOf(SettingsTuiHarness tui, string label)
    {
        var lines = tui.Lines;
        var at = Array.FindIndex(lines, l => l.Contains(label, StringComparison.Ordinal));
        Assert.IsGreaterThanOrEqualTo(0, at, tui.Screen);
        var col = lines[at].IndexOf(label, StringComparison.Ordinal);
        return lines[at + 1].Substring(col + 2, FormRows.LabelWidth - 2).Trim();
    }

    /// <summary>The two detail lines under the status (why a row is disabled, or an error), joined.</summary>
    private static string DetailOf(SettingsTuiHarness tui, string label)
    {
        var lines = tui.Lines;
        var at = Array.FindIndex(lines, l => l.Contains(label, StringComparison.Ordinal));
        var col = lines[at].IndexOf(label, StringComparison.Ordinal);
        return string.Join(" ", new[] { lines[at + 2], lines[at + 3] }.Select(l => l[(col + 2)..].TrimEnd('│', ' ', '▖', '▗', '▘', '▝', '▀', '▄', '▌', '▐', '█').Trim())).Trim();
    }

    [TestMethod]
    public void Typing_a_value_and_pressing_Enter_saves_the_Secret_and_never_shows_it()
    {
        var cfg = CreateWithStore();
        var tui = OpenPage("Secrets", cfg);
        Assert.IsTrue(tui.Shows("SFTP password"), tui.Screen);
        Assert.AreEqual("not set", StatusOf(tui, "SFTP password"), tui.Screen);

        tui.Press(Key.Enter);
        Assert.IsInstanceOfType<TextField>(tui.Focused);
        tui.Type(Value);
        Assert.IsFalse(tui.Screen.Contains(Value), "typed value must be masked");
        tui.Press(Key.Enter);

        Assert.AreEqual(Value, cfg.LoadSecrets().SftpPassword);
        Assert.AreEqual("", tui.FocusedText);
        Assert.AreEqual("set", StatusOf(tui, "SFTP password"), tui.Screen);
        Assert.AreEqual("not set", StatusOf(tui, "SFTP key passphrase"), tui.Screen);
        Assert.IsFalse(tui.Screen.Contains(Value));
    }

    private void Store(string name, string value)
    {
        using var store = SecretStore.Open(StorePath, Alice);
        store.Set(name, value);
    }

    [TestMethod]
    public void The_Save_button_saves_the_typed_value_too()
    {
        var cfg = CreateWithStore();
        var tui = OpenPage("Secrets", cfg);

        tui.Press(Key.Enter);
        tui.Type(Value);
        tui.Press(Key.Tab); // Save
        Assert.IsInstanceOfType<Button>(tui.Focused);
        tui.Press(Key.Enter);

        Assert.AreEqual(Value, cfg.LoadSecrets().SftpPassword);
        Assert.AreEqual("set", StatusOf(tui, "SFTP password"));
    }

    [TestMethod]
    public void Save_does_nothing_for_an_empty_field()
    {
        var cfg = CreateWithStore();
        var tui = OpenPage("Secrets", cfg);

        tui.Press(Key.Enter, Key.Enter);

        Assert.IsNull(cfg.LoadSecrets().SftpPassword);
        Assert.AreEqual("not set", StatusOf(tui, "SFTP password"));
    }

    [TestMethod]
    public void Clear_removes_the_stored_Secret_without_asking()
    {
        Store("sftp-password", Value);
        var cfg = CreateWithStore();
        var tui = OpenPage("Secrets", cfg);
        Assert.AreEqual("set", StatusOf(tui, "SFTP password"), tui.Screen);

        tui.Press(Key.Enter); // field
        tui.Press(Key.Tab);   // Save is disabled with nothing typed, so this is Clear
        Assert.AreEqual("Clear", (tui.Focused as Button)?.Text.Trim(), tui.FocusPath);
        tui.Press(Key.Enter);

        Assert.IsNull(cfg.LoadSecrets().SftpPassword);
        Assert.AreEqual("not set", StatusOf(tui, "SFTP password"));
        Assert.IsEmpty(tui.Dialogs.Confirmations);
        Assert.IsFalse(tui.Screen.Contains(Value));
    }

    [TestMethod]
    public void A_Secret_set_by_an_environment_variable_is_disabled_and_says_so()
    {
        var cfg = CreateWithStore(new() { ["MIRES_SFTP_PASSWORD"] = "from-env-value" });
        var tui = OpenPage("Secrets", cfg);

        Assert.AreEqual("set by an environment variable", StatusOf(tui, "SFTP password"));
        StringAssert.StartsWith(DetailOf(tui, "SFTP password"), "🔒");
        tui.Press(Key.Enter); // lands on the key passphrase: the locked row has no focusable control
        Assert.AreEqual("not set", StatusOf(tui, "SFTP key passphrase"));
        tui.Type("typed");
        Assert.AreEqual("typed", tui.FocusedText);
        tui.Press(Key.Tab.WithShift, Key.Tab.WithShift); // back out of the passphrase row: the locked password row cannot take the focus
        tui.Type("typed-over");

        Assert.AreEqual("from-env-value", cfg.LoadSecrets().SftpPassword);
        Assert.IsFalse(tui.Screen.Contains("from-env-value"));
        Assert.IsFalse(File.Exists(StorePath));
    }

    [TestMethod]
    public void An_unavailable_Secret_Store_disables_the_rows_and_says_why()
    {
        var cfg = CreateWithStore(identity: new FixedIdentity(null, "alice"));
        var tui = OpenPage("Secrets", cfg);

        StringAssert.StartsWith(DetailOf(tui, "SFTP password"), "🔒 This machine has no stable machine identifier");
        tui.Press(Key.Enter);
        Assert.IsNotInstanceOfType<TextField>(tui.Focused, tui.FocusPath);
        Assert.IsFalse(File.Exists(StorePath));
    }

    [TestMethod]
    public void A_Secret_that_cannot_be_decrypted_says_to_re_enter_it_and_can_be_replaced()
    {
        Store("sftp-password", "old");
        var cfg = CreateWithStore(identity: new FixedIdentity("another-machine", "alice"));
        var tui = OpenPage("Secrets", cfg);

        Assert.AreEqual("unreadable", StatusOf(tui, "SFTP password"));
        StringAssert.Contains(DetailOf(tui, "SFTP password"), "re-enter");
        tui.Press(Key.Enter);
        tui.Type(Value);
        tui.Press(Key.Enter);

        Assert.AreEqual("set", StatusOf(tui, "SFTP password"));
    }

    [TestMethod]
    public void Saving_a_Secret_leaves_the_page_Save_state_alone()
    {
        var cfg = CreateWithStore();
        var tui = OpenPage("Secrets", cfg);

        tui.Press(Key.Enter);
        tui.Type(Value);
        tui.Press(Key.Enter);

        Assert.IsFalse(tui.Page.HasChanges);
        Assert.IsTrue(tui.Shows("no changes"), tui.Screen);
    }

    private static IEnumerable<View> Descend(View v) => v.SubViews.SelectMany(c => new[] { c }.Concat(Descend(c)));

    // ---- S3 keys inside a Source form ----

    private SettingsTuiHarness OpenWsiForm(Configuration cfg)
    {
        var tui = OpenPage("Sources", cfg);
        tui.Press(Key.Enter, Key.CursorDown); // into the list, select wsi
        Assert.AreEqual("wsi", tui.Page.Sources[1].Name);
        tui.Press(Key.Enter); // into the form (Name)
        return tui;
    }

    /// <summary>Tabs until the masked field of the Secret named <paramref name="name"/> has the focus.</summary>
    private static void TabToSecret(SettingsTuiHarness tui, string name)
    {
        static string? Named(View? v) { for (; v is not null; v = v.SuperView) if (v is SecretRow r) return r.Entry.Name; return null; }
        for (var i = 0; i < 30 && !(tui.Focused is TextField && Named(tui.Focused) == name); i++) tui.Press(Key.Tab);
        Assert.AreEqual(name, Named(tui.Focused), tui.FocusPath + "\n" + tui.Screen);
    }

    [TestMethod]
    public void A_saved_S3_Source_shows_its_key_rows_and_a_key_is_saved_from_the_form()
    {
        var cfg = CreateWithStore(new() { ["MIRES_S3_WSI_ACCESS_KEY"] = "ak-env-value" }, withS3: true);
        var tui = OpenWsiForm(cfg);
        Assert.AreEqual("set by an environment variable", StatusOf(tui, "Access key"));
        Assert.AreEqual("not set", StatusOf(tui, "Secret key"), tui.Screen);

        TabToSecret(tui, "s3-secret-key:wsi");
        tui.Type(Value);
        Assert.IsFalse(tui.Screen.Contains(Value));
        tui.Press(Key.Enter);

        Assert.AreEqual(Value, cfg.LoadSecrets().S3("wsi")!.SecretKey);
        Assert.AreEqual("ak-env-value", cfg.LoadSecrets().S3("wsi")!.AccessKey);
        Assert.AreEqual("set", StatusOf(tui, "Secret key"), tui.Screen);
        Assert.IsFalse(tui.Screen.Contains(Value));
        Assert.IsFalse(tui.Screen.Contains("ak-env-value"));
        Assert.IsFalse(tui.Page.HasChanges, "a Secret is saved at once, apart from the page Save");
    }

    [TestMethod]
    public void A_stored_S3_key_can_be_cleared_from_the_form()
    {
        Store("s3-access-key:wsi", "ak-stored");
        var cfg = CreateWithStore(withS3: true);
        var tui = OpenWsiForm(cfg);
        Assert.AreEqual("set", StatusOf(tui, "Access key"), tui.Screen);

        TabToSecret(tui, "s3-access-key:wsi");
        tui.Press(Key.Tab); // Clear (Save is disabled)
        Assert.AreEqual("Clear", (tui.Focused as Button)?.Text.Trim(), tui.FocusPath);
        tui.Press(Key.Enter);

        Assert.IsNull(cfg.LoadSecrets().S3("wsi")?.AccessKey);
        Assert.AreEqual("not set", StatusOf(tui, "Access key"));
    }

    [TestMethod]
    public void A_new_S3_Source_has_no_key_rows_until_it_is_saved_and_then_gets_them()
    {
        var cfg = CreateWithStore();
        var tui = OpenPage("Sources", cfg);
        tui.Press(Key.Enter, Key.Tab, Key.Enter); // Add: new Source, cursor in Name
        tui.Type("scans");
        var added = tui.Page.Sources[1];
        added.Type = SourceType.S3;
        added.Endpoint = "https://s3.example.org";
        added.Bucket = "b";
        tui.Draw();

        Assert.IsTrue(tui.Shows("Endpoint URL"), tui.Screen);
        Assert.IsFalse(tui.Shows("Access key"), tui.Screen);
        Assert.IsTrue(tui.Shows("Save the Source"), tui.Screen);

        tui.Press(Key.S.WithCtrl);
        tui.Draw();
        // a save reloads the Sources and selects the first again; select the new one
        var list = Descend(tui.Window).OfType<ListView>().Last();
        list.SelectedItem = 1;
        tui.Draw();

        Assert.IsFalse(tui.Page.HasChanges, string.Join("|", tui.Page.Warnings.Concat(tui.Page.OtherErrors)) + tui.Window.StatusText);
        Assert.IsTrue(tui.Shows("Access key"), tui.Screen);
        Assert.IsTrue(tui.Shows("Secret key"), tui.Screen);
        Assert.IsFalse(tui.Shows("Save the Source"), tui.Screen);
    }

    [TestMethod]
    public void Typing_in_the_Name_of_a_saved_S3_Source_keeps_the_focus()
    {
        var cfg = CreateWithStore(withS3: true);
        var tui = OpenWsiForm(cfg);

        tui.Type("x");

        Assert.AreEqual("x", tui.FocusedText); // the field selects its text on focus, so typing replaces the name
        Assert.AreEqual("x", tui.Page.Sources[1].Name);
        Assert.IsFalse(tui.Shows("Access key"), "renamed, so the keys are not the saved Source's any more");
    }
}

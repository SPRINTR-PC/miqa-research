using System;
using System.Collections.Generic;
using System.Collections.Specialized;
using System.Linq;
using MiresSftpUploader.ViewModels;
using Terminal.Gui.ViewBase;
using Terminal.Gui.Views;

namespace MiresSftpUploader.SettingsTui.Pages;

/// <summary>
/// The Sources page: a list of Sources with Add/Remove and, beside it, the form of the selected Source (Directory: path; S3: endpoint, bucket,
/// prefix, region, force path style; both: optional Remote Path). A locked Sources list disables Add and Remove and says why.
/// The per-Source Archive Rules open in a dialog (<see cref="ITuiDialogs.EditArchiveRules"/>).
/// </summary>
public static class SourcesPage
{
    public const string Title = "Sources";

    public static void Register(PageCatalog catalog) =>
        catalog.Register(new PageDefinition(Title, Badge, ctx => new SourcesView(ctx)));

    private static string Badge(SettingsPageViewModel vm) =>
        vm.Sources.Any(s => s.HasError) ? "!" : vm.SourcesChanged ? "●" : vm.SourcesLocked ? "L" : "";

    /// <summary>One list row: enabled mark, changed marker, name, type, problem mark.</summary>
    public static string Row(SourceEditorViewModel s) =>
        $"{(s.Enabled ? "✓" : "–")} {(s.IsChanged ? "● " : "")}{(s.Name.Length == 0 ? "(new)" : s.Name)} [{s.TypeName}]{(s.HasError ? " !" : "")}";

    private sealed class SourcesView : View
    {
        private readonly PageContext _ctx;
        private readonly MasterDetail _master;

        public SourcesView(PageContext ctx)
        {
            _ctx = ctx;
            Width = Dim.Fill();
            Height = Dim.Fill();
            CanFocus = true;
            TabStop = TabBehavior.NoStop;
            var vm = ctx.Vm;
            _master = new MasterDetail(
                () => vm.Sources.Select(Row).ToList(),
                () => vm.AddSourceCommand.Fire(this),
                i => vm.RemoveSourceCommand.Fire(vm.Sources[i], this),
                i => Form(vm.Sources[i]),
                vm.SourcesEditable,
                vm.SourcesLocked ? "Sources are locked: set by an environment variable or a Machine Config you cannot write." : null);
            Add(_master);
            vm.Sources.CollectionChanged += OnSourcesChanged;
        }

        private void OnSourcesChanged(object? s, NotifyCollectionChangedEventArgs e)
        {
            _master.ItemsChanged();
            _ctx.RefreshChrome();
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing) _ctx.Vm.Sources.CollectionChanged -= OnSourcesChanged;
            base.Dispose(disposing);
        }

        private FormPane Form(SourceEditorViewModel s)
        {
            FormPane pane = null!;
            pane = new FormPane(Rows(s));
            s.PropertyChanged += (_, e) =>
            {
                _master.Reload();
                _ctx.RefreshChrome();
                if (e.PropertyName == nameof(SourceEditorViewModel.Type)) Retype(pane, s);
                else if (e.PropertyName is nameof(SourceEditorViewModel.AccessKey) or nameof(SourceEditorViewModel.SecretKey)) Rekey(pane, s);
                else if (e.PropertyName == nameof(SourceEditorViewModel.MoveLayout)) Relayout(pane, s);
            };
            return pane;
        }

        /// <summary>Type changed: rebuild the rows for the new type on the next loop iteration (the drop-down that raised it is still running), keeping the focus on Type.</summary>
        private void Retype(FormPane pane, SourceEditorViewModel s) =>
            _ctx.App.Invoke(() =>
            {
                pane.ReplaceRows(Rows(s));
                if (pane.Rows.Count > 1) FocusLevels.FocusFirstInput(pane.Rows[1]);
            });

        /// <summary>
        /// The key entries appeared, went away or were swapped (the Source was saved, renamed or retyped): rebuild the rows on the next loop
        /// iteration so the key rows match, and put the focus back on the row it was on.
        /// </summary>
        private void Rekey(FormPane pane, SourceEditorViewModel s) =>
            _ctx.App.Invoke(() =>
            {
                var shown = pane.Rows.OfType<SecretRow>().Select(r => r.Entry).ToList();
                var wanted = new[] { s.AccessKey, s.SecretKey }.OfType<SecretEntryViewModel>().ToList();
                if (shown.SequenceEqual(wanted) && (wanted.Count > 0 || pane.Rows.Any(KeysNote))) return;
                var focused = pane.MostFocused;
                var at = focused is null ? -1 : pane.Rows.ToList().FindIndex(r => r == focused || r.SubViews.Contains(focused) || focused.SuperView == r);
                pane.ReplaceRows(Rows(s));
                if (at >= 0 && at < pane.Rows.Count) FocusLevels.FocusFirstInput(pane.Rows[at]);
            });

        /// <summary>A Move was switched on or off: show or hide its fields on the next loop iteration, keeping the focus on the row that was focused.</summary>
        private void Relayout(FormPane pane, SourceEditorViewModel s) =>
            _ctx.App.Invoke(() =>
            {
                var focused = pane.MostFocused;
                var at = focused is null ? -1 : pane.Rows.ToList().FindIndex(r => r == focused || r.SubViews.Contains(focused) || focused.SuperView == r);
                pane.ReplaceRows(Rows(s));
                if (at >= 0 && at < pane.Rows.Count) FocusLevels.FocusFirstInput(pane.Rows[at]);
            });

        private static bool KeysNote(View row) => row is Label { Text: var t } && t.StartsWith(KeysPending, StringComparison.Ordinal);

        private const string KeysPending = "Save the Source to set its access and secret keys here";

        private IEnumerable<View> Rows(SourceEditorViewModel s)
        {
            var e = s.IsEditable;
            var rows = new List<View>
            {
                FormRows.TextRow("Name", () => s.Name, v => s.Name = v, e),
                FormRows.ChoiceRow("Type", SettingsPageViewModel.SourceTypes, () => s.TypeName, v => s.TypeName = v, e),
                FormRows.ToggleRow("Enabled", () => s.Enabled, v => s.Enabled = v, e),
            };
            if (s.IsDirectory) rows.Add(FormRows.PathRow("Directory path", () => s.Path, v => s.Path = v, e));
            else
            {
                rows.Add(FormRows.TextRow("Endpoint URL", () => s.Endpoint, v => s.Endpoint = v, e));
                rows.Add(FormRows.TextRow("Bucket", () => s.Bucket, v => s.Bucket = v, e));
                rows.Add(FormRows.TextRow("Prefix", () => s.Prefix, v => s.Prefix = v, e));
                rows.Add(FormRows.TextRow("Region (optional)", () => s.Region, v => s.Region = v, e));
                rows.Add(FormRows.ToggleRow("Force path style", () => s.ForcePathStyle, v => s.ForcePathStyle = v, e));
            }

            rows.Add(FormRows.TextRow("Remote Path (optional)", () => s.RemotePath, v => s.RemotePath = v, e));
            rows.Add(FormRows.Note("{date}, {time}, {year}, {month} and {day} are replaced (UTC, start of the Run)."));
            if (s.IsS3) rows.AddRange(S3KeyRows(s));
            rows.AddRange(MoveRows(s, s.OnSuccess, "Move uploaded files", "successfully uploaded files"));
            rows.AddRange(MoveRows(s, s.OnFailure, "Move failed files", "files that failed"));
            rows.Add(FormRows.Btn($"Archive Rules for this Source ({s.ArchiveRules.Rules.Count})…",
                () => _ctx.Dialogs.EditArchiveRules("Archive Rules for " + (s.Name.Length == 0 ? "(new Source)" : s.Name), s.ArchiveRules)));
            rows.Add(Problem(s));
            return rows;
        }

        /// <summary>
        /// The Post-upload Move of one outcome: a switch and, while it is on, where the files go (a directory, or an S3 bucket and prefix).
        /// Each outcome has its own location, so successful and failed files can be kept apart.
        /// </summary>
        private static IEnumerable<View> MoveRows(SourceEditorViewModel s, MoveTargetEditorViewModel m, string label, string what)
        {
            var e = s.IsEditable;
            yield return FormRows.ToggleRow(label, () => m.Move, v => m.Move = v, e);
            if (!m.Move) yield break;
            if (s.IsDirectory) yield return FormRows.PathRow("  Move to", () => m.Path, v => m.Path = v, e);
            else
            {
                yield return FormRows.TextRow("  Bucket", () => m.Bucket, v => m.Bucket = v, e);
                yield return FormRows.TextRow("  Prefix", () => m.Prefix, v => m.Prefix = v, e);
            }
            yield return FormRows.Note($"  The {what} leave the Source for here once the Run is done; nothing is overwritten.");
        }

        /// <summary>
        /// The S3 access and secret key <see cref="SecretRow"/>s, between the Remote Path and the Archive Rules button. The entries are null until
        /// the Source is saved (they are stored under its saved name), so until then a note says so; <see cref="Rekey"/> swaps it for the rows.
        /// </summary>
        private IEnumerable<View> S3KeyRows(SourceEditorViewModel s) =>
            s.AccessKey is { } access && s.SecretKey is { } secret
                ? [new SecretRow(access), new SecretRow(secret)]
                : [FormRows.Note(KeysPending + " (Ctrl+S); they are stored under its saved name.")];

        private static View Problem(SourceEditorViewModel s)
        {
            var label = new Label { Width = Dim.Fill(1), Height = 2 };
            void Show()
            {
                label.Text = s.HasError ? "✗ " + s.Error : s.HasWarning ? "! " + s.Warning : "";
                label.SetScheme(s.HasError ? Theme.Error : Theme.Locked);
            }

            Show();
            s.PropertyChanged += (_, _) => Show();
            return label;
        }
    }
}

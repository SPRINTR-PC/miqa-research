using System;
using System.Collections.Generic;
using Terminal.Gui.Views;

namespace MiresSftpUploader.SettingsTui;

/// <summary>
/// A text box for a local path. <see cref="TryComplete"/> (called by <see cref="FormPane"/> on Tab) applies <see cref="PathCompletion"/>
/// to the text and keeps the candidates of an ambiguous completion until the next edit or until the box loses the focus.
/// </summary>
public sealed class PathTextField : TextField
{
    private readonly Func<string, PathCompletion.Result> _complete;
    private bool _completing;

    public PathTextField(Func<string, PathCompletion.Result>? complete = null)
    {
        _complete = complete ?? PathCompletion.CompleteLocal;
        TextChanged += (_, _) => { if (!_completing) SetCandidates([]); };
        HasFocusChanged += (_, e) => { if (!e.NewValue) SetCandidates([]); };
    }

    /// <summary>The names offered by the last ambiguous completion; empty otherwise.</summary>
    public IReadOnlyList<string> Candidates { get; private set; } = [];

    public event EventHandler? CandidatesChanged;

    /// <summary>Completes the text; false when there is nothing to complete (the caller then moves to the next field).</summary>
    public bool TryComplete()
    {
        var before = Text;
        var result = _complete(before);
        if (!result.HasEffect(before)) return false;
        _completing = true;
        try
        {
            if (result.Text != before)
            {
                Text = result.Text;
                InsertionPoint = result.Text.Length;
            }
        }
        finally
        {
            _completing = false;
        }

        SetCandidates(result.Candidates);
        return true;
    }

    private void SetCandidates(IReadOnlyList<string> candidates)
    {
        if (Candidates.Count == 0 && candidates.Count == 0) return;
        Candidates = candidates;
        CandidatesChanged?.Invoke(this, EventArgs.Empty);
    }
}

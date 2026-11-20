using System.Collections.Generic;
using MiresSftpUploader.Core;
using MiresSftpUploader.ViewModels;
using Terminal.Gui.Views;

namespace MiresSftpUploader.Tui;

/// <summary>
/// The Run's file list as a table: reads <see cref="UploadPageViewModel.Files"/> live and never copies a row, so the table only costs what it draws
/// (a flat few milliseconds up to 100k rows, as long as <c>UseAllRowsForContentCalculation</c> stays false).
/// </summary>
public sealed class FileRowsSource(IReadOnlyList<FileRowViewModel> rows) : ITableSource
{
    public string[] ColumnNames { get; } = ["", "Source", "File", "Status"];

    public int Columns => 4;

    public int Rows => rows.Count;

    /// <summary>
    /// The width the Status column has on screen; an uploading row drops its bar when the bar does not fit (see <see cref="TuiStatusCell"/>).
    /// The page sets it on every refresh.
    /// </summary>
    public int StatusWidth { get; set; } = int.MaxValue;

    public object this[int row, int col]
    {
        get
        {
            if (row < 0 || row >= rows.Count) return "";
            var r = rows[row];
            return col switch
            {
                0 => OutcomeSymbols.Of(r.Outcome),
                1 => r.Source,
                2 => r.Path,
                _ => TuiStatusCell.Of(r, StatusWidth),
            };
        }
    }
}

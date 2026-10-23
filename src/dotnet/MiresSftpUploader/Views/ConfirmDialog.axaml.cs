using Avalonia.Controls;

namespace MiresSftpUploader.Views;

/// <summary>A yes/no dialog; closes with true when the user confirms, false otherwise.</summary>
public partial class ConfirmDialog : Window
{
    public ConfirmDialog() => InitializeComponent();

    public ConfirmDialog(string title, string message) : this()
    {
        Title = title;
        this.FindControl<TextBlock>("TitleText")!.Text = title;
        this.FindControl<TextBlock>("MessageText")!.Text = message;
        this.FindControl<Button>("CancelButton")!.Click += (_, _) => Close(false);
        this.FindControl<Button>("ConfirmButton")!.Click += (_, _) => Close(true);
    }
}

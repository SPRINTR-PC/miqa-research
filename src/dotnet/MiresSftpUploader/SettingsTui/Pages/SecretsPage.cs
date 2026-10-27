namespace MiresSftpUploader.SettingsTui.Pages;

/// <summary>
/// The Secrets page: the SFTP password and the key passphrase as <see cref="SecretRow"/>s. A Secret is saved to the Secret Store at once,
/// independent of the page Save (and not part of its change tracking). The S3 keys live in each S3 Source's form on the Sources page.
/// </summary>
public static class SecretsPage
{
    public const string Title = "Secrets";

    public static void Register(PageCatalog catalog) =>
        catalog.Register(new PageDefinition(
            Title,
            _ => "",
            ctx => new FormPane(
            [
                FormRows.Note("Saved to the Secret Store at once. A stored value is never shown."),
                new SecretRow(ctx.Vm.SftpPassword),
                new SecretRow(ctx.Vm.SftpKeyPassphrase),
                FormRows.Note("The S3 access and secret keys are set in the form of each S3 Source, under Sources."),
            ])));
}

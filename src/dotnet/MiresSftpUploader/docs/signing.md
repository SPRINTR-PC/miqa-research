# Enabling code signing

Release builds are unsigned. The hooks exist but are disabled: nothing is signed unless `SignWindows` `SignMac` or `SignLinux` is `true`. They are read at publish time only, as MSBuild properties (`-p:Name=value`) or environment variables of the same name, never from `appsettings.json`. The targets are in `Signing.targets`.

| Property | Needed when | Meaning |
|---|---|---|
| `SignWindows` | | `true` to run `signtool` on the `win-x64` executable |
| `WindowsSignCertThumbprint` | `SignWindows` | thumbprint of the Authenticode certificate in the certificate store |
| `WindowsSignTimestampUrl` | `SignWindows` | RFC 3161 timestamp server |
| `SignMac` | | `true` to run `codesign` and `notarytool` on the `osx-arm64` executable and the `MiresSftpUploader.app` bundle |
| `MacSignIdentity` | `SignMac` | Developer ID Application identity |
| `MacEntitlements` | `SignMac` | path to the entitlements file; use `macOS.entitlements` (unused until now) |
| `MacNotarizeProfile` | `SignMac` | `notarytool` keychain profile (`xcrun notarytool store-credentials`) |
| `SignLinux` | | `true` to run `cosign sign-blob` on the `linux-x64` / `linux-arm64` executable |
| `CosignKey` | optional | cosign private key file or KMS URI; empty means keyless signing with an OIDC login |

The inputs marked required are needed only for the RID being published. If signing is requested and an input is missing, the `MiresGuardSigning` target fails the publish and names the missing property.

## Steps

1. Windows: install the Windows SDK (`signtool`) on the build machine and the certificate in its store. Run `publish.ps1` (or `publish.sh`) with `SignWindows=true` and both Windows inputs set.
2. macOS: build on a Mac with the Developer ID certificate in the keychain and a stored notarization profile. Set `SignMac=true` and the three Mac inputs.
3. Signing runs after the publish, before the script packages the output. A bare executable cannot be stapled; Gatekeeper checks notarization online.
4. Linux: install [cosign](https://docs.sigstore.dev/cosign/installation/) on the build machine and set `SignLinux=true`. This writes `MiresSftpUploader.cosign.bundle` next to the executable. Without `CosignKey` the signing is keyless: cosign opens an OIDC login (in CI it uses the workflow's identity token) and records the signature in the Rekor log. With `CosignKey` (and `COSIGN_PASSWORD` for an encrypted key file) it signs with your key.
   Users verify with `cosign verify-blob --bundle MiresSftpUploader.cosign.bundle --certificate-identity <signer> --certificate-oidc-issuer <issuer> MiresSftpUploader` (keyless), or `--key cosign.pub` (key).
5. Azure Trusted Signing or AzureSignTool can replace the `signtool` command in the `MiresSignWindows` target.

The signing commands have not been exercised yet; try them on a release candidate first.

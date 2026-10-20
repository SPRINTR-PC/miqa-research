# Releases are untrimmed, self-contained single files

Each of the four targets (`win-x64`, `linux-x64`, `linux-arm64`, `osx-arm64`) ships as one self-contained executable with native libraries self-extracted and compression off, next to an editable `appsettings.json`. Trimming stays off because AWSSDK, SSH.NET, NLog configuration binding, `Microsoft.Data.Sqlite` and compiled bindings use reflection; it is a possible later size optimisation, not a v1 risk worth taking. Signing is prepared but disabled (`docs/signing.md`).

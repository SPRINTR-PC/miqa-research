# Glossary Map

## Contexts

- [MiqaResearch](./src/MiqaResearch/GLOSSARY.md): the Django research platform (authentication, projects, ETL, viewers, charts)
- [MiresSftpUploader](./src/dotnet/MiresSftpUploader/GLOSSARY.md): the Avalonia desktop and headless tool that uploads files to a MIRES-owned SFTP server

## Relationships

- **MiresSftpUploader → MIRES SFTP server**: the uploader is the only writer; consumers of the uploaded files validate them against the Manifest it uploads. The two contexts share no types.

<div style="width: 100%;">
<img src="src/MiqaResearch/static/icons/miqa-research-logo-full.svg" alt="MIQA Research" style="width: 100%; max-width: 50rem;"/>
</div>

[![.NET Test](https://github.com/josef/miqa-research/actions/workflows/dotnet-test.yml/badge.svg)](https://github.com/josef/miqa-research/actions/workflows/dotnet-test.yml)

# MIQA-research
A Django based web application for managing storage and export of research data, enabling connecting data to research project.

## Configuration management

### .NET applications/services
For .NET applications that are part of MIQA Research, the _appsettings.json_ file that is included with the compiled application/service can be used to configure the application.

All configurations found in that file can also be configured with environment variables. The environment variables should be named as the structure of the settings in the appsettings.json file and prefixed with _MIRES_. For example, the AE-title for the DICOM receiver could be configured by the environment variable _MIRES_DICOMRECEIVER_AETITLE_.

### DICOM Receiver (CSTORE SCP)
To setup TLS for the DICOM receiver, the _CertificatePath_ and, optionally, _CertificatePassword_ settings in the _appsettings_ can be used. The certificate for which the _CertificatePath_ points to should be a valid **.pfx** or **.p12** file.

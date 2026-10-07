(heading-api-clients)=
# API Clients

The **API Clients** tab of a research project lists the machine clients that read the project's
images over the DICOMweb (WADO) API, for example an analysis pipeline. Only a project **Admin**
(or a superuser) sees this tab.

Each client is bound to this project for good. You can narrow it to one **Site**: it then only
reads images of participants with a consent at that Site. With no Site it reads every participant
of the project. A client belongs to the project, not to you: it keeps working if you leave the
project.

(heading-api-clients-issue)=
## Issuing a client

Select **New API client**, give it a name, optionally pick a Site, and select **Issue client**.
The page shows the **Client ID** and **Client secret**. Copy the secret now: it is not stored
in readable form and is never shown again. If it is lost, rotate it.

By default a client only gets **de-identified** metadata and image frames. Tick
**Raw DICOM access (dicom:raw)** only if the client really needs the original files: they contain
the participant's full identity (PHI). Granting and removing raw access are recorded in the audit
log as data-access events.

(heading-api-clients-manage)=
## Changing, rotating and revoking

- **Edit** changes the Site or the raw access. The project can't be changed.
- **Rotate secret** creates a new secret. The old secret, and every token issued with it, stops
  working at once.
- **Revoke** deletes the client. Its tokens stop working at once.

Every change is recorded in the audit log with your name.

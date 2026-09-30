# Domain Model — MiqaResearch

## Glossary

### Authentication Framework
The configurable system that determines how users authenticate to the MiqaResearch
application. Controlled at runtime by the `MIRES_AUTHENTICATION_FRAMEWORK` environment
variable, which accepts a comma-separated list of modes: `local` (email/password),
`oidc` (generic OIDC via allauth), `adfs` (Microsoft ADFS via allauth), and `yubikey`
(WebAuthn/passkey MFA via allauth). Modes can be combined (e.g., `"oidc,yubikey"` for
two-factor authentication). In development (`DEBUG=True`), local email/password login
is always available in addition to any configured OIDC provider. In production, only
the configured modes are active.

### OIDC (OpenID Connect)
An identity layer on top of the OAuth 2.0 protocol. Used for federated
login where an external Identity Provider (IdP) authenticates the user and
returns claims (e.g., email, name, roles) to the application. In MiqaResearch,
OIDC is integrated via **django-allauth**'s `SocialAccount` framework with the
`openid-connect` provider, which supports both generic OIDC servers and
Microsoft ADFS.

### ADFS (Active Directory Federation Services)
Microsoft's OIDC-compliant identity provider. From the application's perspective,
ADFS is treated as a standard OIDC provider — its discovery and token endpoints
are configured via standard OIDC URLs. No special library or code path is needed
beyond generic OIDC configuration.

### EID (E-identitet / Svensk E-identitet)
A separate, custom authentication flow that connects to the "Svensk E-identitet"
OIDC/SAML broker to provide SITHS and BankID login. This is **distinct** from the
OIDC/ADFS authentication framework and is currently out of scope for the
authentication redesign. Preserved as-is for now.

### MFA (Multi-Factor Authentication)
Secondary authentication layered on top of primary login. MiqaResearch uses
django-allauth's MFA module with WebAuthn (passkey/hardware security key) as the
supported method. Configurable via `MFA_SUPPORTED_TYPES` and
`MFA_WEBAUTHN_ALLOW_INSECURE_ORIGIN`.

### Session
A user's authenticated period, managed by Django's session framework. Sessions
are stored server-side and identified by a session key in a cookie. In production,
sessions are subject to two expiration policies:
- **Maximum absolute lifetime**: the session expires after N hours regardless of
  activity (configurable via `MIRES_SESSION_COOKIE_AGE`).
- **Sliding inactivity timeout**: the session expires after N minutes of
  inactivity (configurable via `MIRES_SESSION_IDLE_TIMEOUT`).
In development (`DEBUG=True`), neither timeout is enforced to reduce friction.

### Audit Log
A record of authentication-related events written to the `mires_audit_log`
table (the `AuditLog` model). Each entry captures: event type (login, logout,
session expired, login failed), the authenticated user, IP address, session key,
authentication method (oidc, local, mfa), timestamp, and optional metadata.
Events are emitted via Django's built-in `user_logged_in`, `user_logged_out`,
and `user_login_failed` signals, plus the inactivity-timeout middleware.
It also records **data-access events** — opening a participant's data view,
opening the DICOM viewer, each image-series fetch, PROM Signing, re-linking a
PROM to another participant, and every Identity Reveal — which are kept far
longer than authentication events (see ADR 0024).

### Bearer Token
A long-lived API credential (distinct from OAuth2 access tokens) stored as a
hashed value in the `mires_bearer_token` table. Generated via
`BearerToken.generate_token()`. The custom `BearerToken` model coexists with
django-oauth-toolkit's `AccessToken` model but serves a different purpose.

### JWT (JSON Web Token)
A compact, self-contained token format used for API authentication. In
MiqaResearch, JWT support is provided by **django-oauth-toolkit**'s native JWT
token encoding (configured via `OAUTH2_PROVIDER` settings), not a separate
JWT library. API requests are authenticated via the `ClientCredentialsAuth`
class, which validates JWT-encoded access tokens against scope requirements.

### Social Account
A user account linked to an external identity provider (e.g., an OIDC IdP)
via django-allauth's `SocialAccount` framework. When an OIDC user authenticates
for the first time, a Django user is auto-provisioned from the IdP's claims
(email, first name, last name). Role-to-group mapping is applied from
database-stored `OIDCRoleMapping` records (seeded from the `MIRES_OIDC_ROLE_MAPPING`
environment variable if no database records exist yet).

### Role Mapping
The process of translating OIDC role claims (e.g., a `role` claim in the ID
token) to Django group assignments. Stored in the `OIDCRoleMapping` database
model (mapping IdP role strings to Django `Group` instances). Initial values
can be seeded from the `MIRES_OIDC_ROLE_MAPPING` JSON environment variable on
first run. Applied during OIDC user provisioning.

### OIDC Provider Configuration
A single OIDC provider per deployment, configured via environment variables:
`MIRES_OIDC_DISCOVERY_URL` (the provider's OIDC discovery document URL),
`MIRES_OIDC_CLIENT_ID`, and `MIRES_OIDC_CLIENT_SECRET`. For Microsoft ADFS,
the discovery URL is at `https://adfs.example.com/adfs/.well-known/openid-configuration`.
Secrets are fetched from Vault in production, environment variables in development.

### OIDC Authentication Framework
The `MIRES_AUTHENTICATION_FRAMEWORK` environment variable historically controlled
which OIDC library was used (`"adfs"` for `django_auth_adfs`, `"oidc"` for
`mozilla_django_oidc`). The old `"yubikey"` default did not activate either
branch, falling through to local-only auth. This is being replaced by a
mode-based system: `MIRES_AUTHENTICATION_FRAMEWORK` can be `"local"` (no OIDC),
`"oidc"` (generic OIDC via allauth), or `"adfs"` (OIDC with ADFS-specific
endpoint derivation). The `"oidc"` and `"adfs"` modes are now both handled by
allauth's SocialAccount with the same code path; the difference is only in how
the discovery URL is derived. A deprecation warning is emitted when the old
`"adfs"` or `"oidc"` values are used without `MIRES_OIDC_DISCOVERY_URL`.

### OIDC Authentication Modes
The complete set of authentication modes available per deployment, combinable
with MFA (see below):
- **local**: No OIDC. Username/password via django-allauth only. Used in
  development when no IdP is configured.
- **oidc**: Generic OIDC provider via allauth SocialAccount. Configured via
  `MIRES_OIDC_DISCOVERY_URL`. Available in both development and production.
- **adfs**: Microsoft ADFS as OIDC provider. Same allauth code path as `"oidc"`
  but derives discovery URL from `MIRES_ADFS_AUTHORITY` with ADFS-specific path
  (`/adfs/.well-known/openid-configuration`).
- **yubikey**: WebAuthn/passkey-based authentication via allauth MFA. Can be
  used as a standalone login method (if `MFA_PASSKEY_LOGIN_ENABLED = True`) or
  as a second factor after OIDC or local login. This mode can be combined with
  `"oidc"` or `"adfs"` modes to provide two-factor authentication in production
  installations.

### MFA (WebAuthn / Passkey)
A cross-cutting authentication concern that provides an additional verification
step using hardware security keys or platform authenticators (e.g., Touch ID,
Windows Hello). Configurable via `MFA_SUPPORTED_TYPES = ["webauthn"]` and
`MFA_PASSKEY_LOGIN_ENABLED = True`. MFA can be combined with any primary
authentication mode (`oidc`, `adfs`, `local`) to provide two-factor
authentication. In production, operators can require MFA after OIDC login by
setting `ACCOUNT_MFA_REQUIRED = True` (via django-allauth). The `yubikey`
authentication framework mode enables MFA as a standalone login option on the
login page — useful when OIDC is not available but hardware-key authentication
is desired.

### Login Page Rendering
The login page (`templates/account/login.partial.html`) conditionally renders
sections based on configuration:
- **OIDC section**: Shown when `MIRES_OIDC_DISCOVERY_URL` is configured or
  `MIRES_AUTHENTICATION_FRAMEWORK` is `"oidc"` or `"adfs"`. Displays a single
  "Sign in with SSO" button (or `MIRES_OIDC_PROVIDER_DISPLAY_NAME` if set).
  Rendered server-side via template conditionals — not hidden via CSS.
- **YubiKey/Passkey section**: Shown when `MIRES_AUTHENTICATION_FRAMEWORK`
  includes `"yubikey"` or when MFA is available. Provides a "Sign in with Passkey"
  link to allauth's `mfa_reauthenticate` flow for users who have previously
  registered a WebAuthn credential. This section can appear alongside the OIDC
  section, enabling MFA as an additional option.
- **SITHS/BankID section**: Always shown (existing EID flow, deferred for redesign).
- **Local email/password section**: Always shown when `DEBUG=True` or when
  `MIRES_AUTHENTICATION_FRAMEWORK=local`. Hidden in production otherwise.

### Classic Path
The Tesseract-OCR-based half of the PROM OCR pipeline (`field_matching.py` +
`mark_detection.py`): fuzzy label-anchor search locates each field's region
across all pages, then ink-density thresholding reads checkbox/radio/
ranged-radio marks. Distinguished from the VLM Fallback, which reads a page
image directly via a vision-language model. See `docs/prom-ocr-handoff.md`.

### VLM Fallback / Escalation
The second half of the PROM OCR pipeline: a field the Classic Path couldn't
confidently resolve is **escalated** — batched with other escalated fields on
the same page into one call to a vision-language model (Ollama). Which
fields escalate is governed by the **escalation contract** (`should_escalate`
in `vlm_fallback.py`): confidence thresholds per field type, tuned in issue
#18. See `docs/prom-ocr-handoff.md`.

### OCR Pipeline Mode
A global, deployment-level setting selecting how the PROM OCR pipeline
combines the Classic Path and the VLM Fallback. Two modes:
- **Hybrid Mode** (default, the pipeline shipped by epic #10): Classic Path
  runs in full, and only fields the escalation contract flags are sent to
  the VLM Fallback.
- **VLM-Only Mode** (opt-in, for installations with capable-enough
  hardware): field-matching still runs (page localization, and text
  fallback for non-mark fields), but mark detection is skipped and every
  field is escalated unconditionally — the VLM Fallback becomes the
  pipeline's primary source of truth rather than a fallback for the
  minority of low-confidence fields. Chosen because a benchmark (issue #17)
  measured a full-page VLM pass as more accurate (90.2%) than Hybrid Mode's
  measured end-to-end accuracy (68.3%, issue #50) — at the cost of
  substantially higher latency, since every page now requires a VLM call
  rather than only the escalated minority.
_Avoid_: "VLM-primary" (use VLM-Only Mode)

### GPU Acceleration (OCR)
A separate opt-in setting for the Ollama backend used by the VLM Fallback,
independent of OCR Pipeline Mode (though most relevant to VLM-Only Mode,
where every page requires a VLM call). Relaxes epic #10's original
"CPU-only, no GPU" hard server requirement for installations that opt in.

### Research Project
A study being run in MiqaResearch, represented by the `ResearchProject` model
(`name`, `description`). A user's involvement in a Research Project is recorded
per-role via `ResearchProjectUserRoleMap` (Admin, PI, Investigator, Data Manager,
Contributor, Annotator).

### Site
A physical location where study participants are recruited and consented,
represented in code by the `Clinic` model. Domain language and UI should say
"Site"; the `Clinic` model name is a historical artifact of the model
predating this term. Which Sites participate in which Research Project is
recorded explicitly — see Project Site.
_Avoid_: Clinic (in prose/UI — keep it only as the existing model/table name)

### Project Site
The explicit link between a Research Project and a Site that participates in
it, configured by an Admin or PI independent of whether any consent data for
that Site exists yet. A Research Project with more than one Project Site is a
**multi-site** project. See ADR 0019.

### Data Collection Goal
A configurable, quantitative target for data gathering on a Research Project —
a project may define several at once, each independently typed by metric
(consent-based, enrollment-based, or imaging-completeness-based) and optionally
scoped to a single Site rather than the whole project. See ADR 0018. Does not
exist in the codebase yet; introduced by the Dashboard feature.
_Avoid_: Target, quota

### Site Assignment
The association between a User and a Site within the context of a specific
Research Project, used to determine which Site(s)' status to show that user
on their project dashboard alongside the project-wide view. A User may hold
more than one Site Assignment on the same project. Recorded as the optional
Site on a user's project role; a role with no Site covers every Site of the
project. See ADR 0019 and Participant Visibility.
_Avoid_: Site membership, clinic membership

### Participant Visibility
Which Study Participants a user may see data for within a Research Project:
the union over the user's project roles. Project Admin and Principal
Investigator see every participant regardless of any Site on their role (for
them the Site is only a Site Assignment); for other roles, a role with no Site
sees every participant and a role with a Site sees only participants holding a
consent at that Site. Any consent counts, revoked or not — data gathered while
consent was in force stays viewable. A participant with consents at several
Sites is visible to each of those Sites; one with no consent yet is visible
only to all-Sites users. Every per-participant table, view, and image honours
it; project-wide aggregates (e.g. the "All sites" chart) are not sensitive and
do not.

### Client Binding
The tie between a machine-to-machine API client (client-credentials, no user)
and exactly one Research Project, optionally narrowed to one Site. The client
sees participants as a role with that Site would (see Participant Visibility);
under Blinded Annotation it sees no Annotations or Segmentations. An unbound
client sees no participant data. A binding belongs to the project, not the
person who issued it, and is managed by an Admin or that project's Project
Admin. See ADR 0027.
_Avoid_: client scope, project scope

### Site PI
A principal investigator responsible for one Site of a Research Project. Always
tied to a Site: sees only that Site's participants (see Participant Visibility)
and may sign PROMs for them, but has none of the project-level powers of the
Principal Investigator (e.g. editing Site Assignments or Data Collection Goals).
_Avoid_: Local PI

### Identity Reveal
An explicit, per-request action by which a permitted user displays a Study
Participant's name and personal identifier instead of the alias. Never shown
by default — even to roles allowed to see them — and every reveal is audit
logged. Looking a participant up by exact personal identifier (e.g. when
linking an uploaded PROM form) also counts as a reveal. Permitted: Project
Admin, Principal Investigator, Site PI and Participant Recruiter, only for
participants within their Participant Visibility. A reveal is per participant
and lasts only for the current page; the user must state a reason.
_Avoid_: Unmask, de-pseudonymize

### Data Kind
A kind of research data held per Study Participant that the project's Data
view counts, sizes, and lists — initially Study Participants themselves,
PROM Forms, Dicom Series, Annotations and Segmentations.
Each kind knows its own count, size, per-participant presence, and how its
data is displayed. Several kinds may be carved from the same stored records
(e.g. imaging series vs. annotation/segmentation series). Distinct from ETL
Datatype: a Datatype describes how data *arrives*, a Data Kind describes what
is *held*; a Datatype may name the Data Kind it feeds, but participants, PROM
Forms and viewer-made annotations have no Datatype at all.
_Avoid_: Data type (ambiguous with column/field types)

### PROM Signing
A human reviewer's confirmation that a PROM form's OCR-extracted data —
possibly after manual correction — is correct, recording who signed and when.
Correcting an already-signed form produces a new, unsigned version; the
latest version is authoritative and earlier ones remain as history. A
signature covers the extracted data, not which Study Participant the form
belongs to — re-linking a form does not unsign it.
_Avoid_: Approve, validate (in UI)

### Annotation
A DICOM object (SR or ANN) marking regions, points or measurements on one or
more Dicom Series of a Study Participant, held as its own Dicom Series. Made in
the viewer by an Annotator, Principal Investigator, Site PI or Project Admin,
or arriving through ingestion (then it has no author). A Data Kind.
_Avoid_: Label, markup, measurement (as the object's name)

### Segmentation
A DICOM object (SEG or RTSTRUCT) labelling voxels or contours as structures on
one or more Dicom Series, held as its own Dicom Series. Authored and ingested
like an Annotation. A Data Kind.
_Avoid_: Mask, label map (as the object's name)

### Supersede
Replacing an Annotation or Segmentation with a new version that points to its
predecessor; objects never change in place, and each has one linear version
chain whose head is current. Authors supersede their own; Principal
Investigator, Site PI (in its Sites) and Project Admin may supersede anyone's.
_Avoid_: Edit, overwrite

### Retire
Hiding an Annotation or Segmentation from use while keeping it and its history.
Same rights as Supersede. Only deleting the participant's or project's data
removes it.
_Avoid_: Delete

### Blinded Annotation
A per-project setting (set by Principal Investigator or Project Admin, audit
logged) under which every user sees only their own Annotations and
Segmentations, and ingested ones are hidden. Aggregate counts are unaffected.
_Avoid_: Masked review

### Blinding Reveal
An explicit, audit-logged action by which a Principal Investigator, Site PI or
Project Admin, under Blinded Annotation, shows others' Annotations and
Segmentations for one participant for the current viewer session. Annotators
can never reveal.
_Avoid_: Unblind (as a project-wide switch)

### Spacing Calibration
How trustworthy an image's pixel-to-millimetre scale is: tomographic,
magnification-corrected, detector-plane, ultrasound-region, user-calibrated,
unverified, or absent (measurements in pixels). Shown on every measurement and
saved with it in an Annotation. Uncalibrated measurements are never recorded
as millimetres.
_Avoid_: Pixel spacing (as the trust level), scale

### Related Series
The other Dicom Series of the same Study Participant that the viewer offers
beside the ones it opened, to fuse or to show instead. Limited by Participant
Visibility like any series.
_Avoid_: Study list, other scans

### Fusion
Showing one or more overlay Dicom Series on top of a base series in the viewer,
each with its own window, colormap and opacity. Only series sharing the base's
Frame of Reference can be fused; nothing is registered or resampled into a new
series. Annotations and Segmentations made on a fusion reference every series
in view; a Segmentation's voxel grid is the base's.
_Avoid_: Registration, blend, overlay (as the whole view)

### Study Participant
The person enrolled in a Research Project, represented by the `StudyParticipant`
model. It is the only person/subject identity in this codebase — imaging data
and consent records both hang off the same Study Participant; there is no
separate "Patient" concept. Personally identifying fields (`person_source_value`,
`name`) are encrypted at rest and looked up via a deterministic hash sidecar
rather than plaintext query. Identified pseudonymously per Research Project via
`alias1`.
_Avoid_: Patient, Subject

### Dicom Study
One DICOM study belonging to a Study Participant, represented by the
`DicomStudy` model (`study_instance_uid`). Optionally links to a
`VisitOccurrence`. See Dicom Series.

### Dicom Series
One DICOM series within a Dicom Study, represented by the `DicomSeries` model
(`series_instance_uid`, `modality`). See Dicom File.

### Dicom File
One DICOM instance — a single file, one SOP Instance — within a Dicom Series,
represented by the `DicomFile` model (`sop_instance_uid`). The unit of storage
and WADO retrieval.

### UID Pseudonymization
Per-Research Project deterministic replacement of the UIDs in ingested DICOM
data (Study/Series/SOP Instance/Frame of Reference) with pseudonyms, so stored
records cannot be linked back to the originating hospital PACS identifiers.
The same source UID always yields the same pseudonym within a project and a
different one across projects, keeping intra-project linkage and
duplicate-detection intact. Also called HashUID (CTP-style).
_Avoid_: Anonymization (that strips identifying data without preserving per-project linkage)
See Dicom File.

### De-identification Profile
The single, system-wide set of rules that removes or replaces identifying
attributes in DICOM headers wherever the platform exposes them — the stored
metadata dump and everything served to the viewer or bound machine clients
under `read`. Based on the DICOM PS3.15 Basic Profile, keeping patient
characteristics, full dates, device and institution identity, safe private
attributes and a small set of structural descriptors. Patient name and ID are
replaced by the Study Participant's pseudonym; all instance UIDs undergo UID
Pseudonymization. Not configurable per Research Project. Does not touch pixel
data: burned-in text is only flagged. See ADR 0028.
_Avoid_: PHI tags, sanitizer (implementation), anonymization profile

### Chart Grouping
One of possibly several alternative groupings of the same underlying dataset
that a chart web component's `dataUrl` endpoint can return in a single
response. The viewer switches between Groupings via a dropdown (the existing
`kp-select` component); switching re-renders the chart from the
already-fetched response with no refetch. A response's `groupings` array is
always non-empty — a chart with only one Grouping (length 1) renders without
showing the dropdown at all, rather than the API using a distinct top-level
shape for that case. See ADR 0020. Introduced by the charting web components
effort (wayfinder map: Charting web components (Plotly.js) + serializers:
architecture & API contract spec, #87) — shipped in full, see
`docs/charts-handoff.md`.

### Chart Config
The layout/behaviour settings in a chart API response that are fixed across
every Chart Grouping in that response: the WebGL Threshold override
(`webglThreshold`/`forceRenderer`), Chart Event Callback names
(`eventCallbacks`), and mixed-type subplot layout. Distinct from Chart Data,
which varies per Grouping. See ADR 0020.
_Avoid_: "chart options", "chart settings" (ambiguous with Chart Data's
per-Grouping `labels`)

### Chart Data
The actual trace values inside one Chart Grouping — the per-chart-type
payload (e.g. x/y arrays, categories, node/link lists) plus an optional
`labels` sub-object (axis/legend titles, and an optional `xAxisRange`/
`yAxisRange` override of Plotly's computed autorange) that can differ from one
Grouping to the next, unlike Chart Config which is fixed for the whole
response. See ADR 0020.

### WebGL Threshold
The datapoint-count threshold (`webglThreshold`, default 100) above which a
chart component selects a chart type's WebGL-accelerated Plotly trace variant
instead of the SVG-based default; a `forceRenderer` value of `"svg"`,
`"webgl"`, or `"auto"` bypasses the threshold entirely. Only 4 of the 11
chart types have a WebGL-accelerated trace in the pinned plotly.js version
(line, scatter, bubble, filled area — all via `scattergl`); on the other 7
(pie, bar, histogram, box, heatmap, sankey, 2D density) the property is a
documented no-op rather than being absent from the component's interface, so
every chart type exposes the same config surface. See ADR 0020 and the
[WebGL trace variant research](docs/research/webgl-threshold-plotly-4.1.md).

### Chart Event Callback
A named external JavaScript function, specified in a chart's `dataUrl`
response (`config.eventCallbacks.click` / `.zoom`), that a chart component
invokes on a `plotly_click` or `plotly_relayout` (zoom/pan/reset) event.
Resolution is against a client-side registry (`window.mires.registerChartCallback(name, fn)`,
also available as a module export), never a raw `window[name]` lookup or
`eval` — the host page must explicitly register a name before a component
will call it. A name the API supplies but nobody registered logs one
`console.warn` and no-ops; it never throws. This is the security boundary: a
server-supplied name can at most reference an unregistered no-op or a
function the host page already chose to expose, never make the browser run
code the page didn't opt into. See ADR 0021.
_Avoid_: "chart click handler" (the callback isn't wired per-component in
code — it's named by the API response and resolved at event-fire time)

### Chart Palette
The color/typography system a chart web component resolves from CSS custom
properties into a Plotly layout object at render time (plotly.js has no
native CSS-variable support, so a wrapper reads them via `getComputedStyle`).
Background, text color, and font family come directly from the existing
`--mires-color-background`, `--mires-form-color-text`, and `--form-font-family`
variables. The **categorical** series colors (`--mires-chart-series-1`
through `-8`) are a fixed, pre-validated 8-hue set (the `dataviz` skill's
reference palette) rather than derived at runtime from the two brand hue
variables — colorblind-safety depends on specific hue/lightness combinations
that an arbitrary site-configured brand hue can't be assumed to preserve
(confirmed by running the skill's validator: forcing MiqaResearch's own
primary/secondary hues adjacent in the categorical order fails the dark-mode
CVD floor). The **sequential** ramp (`--mires-chart-sequential-0` through
`-5`, used by heatmap/2D-density), by contrast, is computed live from
`--mires-color-primary-parts` via CSS relative-color syntax — safe because a
single-hue lightness ramp carries no cross-hue CVD risk, unlike the
categorical set. A **diverging** ramp (`--mires-chart-diverging-negative`,
`-neutral`, `-positive` — fixed blue↔red↔gray, per the `dataviz` skill's
diverging-pair guidance) was added for polarity data (e.g. a correlation
heatmap) where a single-hue sequential ramp would hide which side of a
meaningful zero a cell falls on; a chart type opts into it explicitly (e.g.
heatmap's `config.colorScale`) rather than it being a default. **Sankey is a
documented exception** to the "no per-item color override" rule the other
chart types follow (#77's XY series, pie's slices): a Sankey's node count is
open-ended (routinely beyond the categorical set's 8 safe slots), so node
identity was never the "small fixed set of series" case the categorical
palette protects — nodes/links may carry an explicit `color`, defaulting to a
neutral tone (nodes) or a translucent tint of their source node's color
(links) when omitted. See ADR 0022.

### Chart Grid
A single chart web component (`<mires-chart-grid>`) that renders a mix of
different chart types as subplots of one plotly.js figure (one native
subplot/grid layout — never several independently-mounted per-type elements
composited client-side, since plotly.js doesn't support that). Its `dataUrl`
returns one combined response covering every subplot at once: `config`
carries the fixed grid layout (`rows`, `cols`, and each subplot's `type`,
position, and own type-specific config), while each Chart Grouping's `data`
carries one entry per subplot, shaped exactly like that subplot's own
standalone Chart Data (e.g. a `"bar"` subplot's entry matches
`BarChartData`). One Grouping dropdown switches every subplot together —
there is no per-subplot Grouping concept. See ADR 0023.

### Data Table
A single reusable web component (`<data-table>`) that shows one page of rows
fetched from its `dataUrl`, with column headers, multi-column sorting, and
per-column filters. Sorting, filtering, and paging are all performed by the
server; the component only holds the current view state and re-requests. Its
first consumer is the consent statistics table.

### Data Table Definition
The single server-side declaration of a Data Table's columns: for each column
its accessor, label, data type, whether it is sortable, and its filter kind.
It is the one source for both the column metadata sent to the component and
the set of sort and filter requests the server will accept — anything not
declared is rejected.
_Avoid_: Column map, table schema

### Data Table Pagination
The server-side unit that turns a request into one page of a Data Table: it
applies the requested filters and sort, slices the page, and reports the
page position and totals. Paging, sorting, and filtering are one unit, not
separate layers.
_Avoid_: Paginator (that names the generic Django class)

### ETL Datatype
A code-registered kind of incoming data (name, output schema, loader that
persists validated rows into models). Users choose among Datatypes; they never
define them. Scripts return rows matching the Datatype's schema and never write
to the database themselves.
_Avoid_: Data type (ambiguous with column/field types)

### ETL Script
A user-authored program (Python or R, picked by the uploaded file's extension)
that takes staged input files and produces rows for one ETL Datatype. Both
languages follow the same contract: `main(ctx)` yields (Python) or `emit()`s
(R) rows, which are validated against the Datatype's schema in the sandbox. Belongs to a Research Project, managed by
its Admins and Data Managers. Built-in (default) scripts are global and
read-only. Every save produces an immutable **Script Version**.

### Script Version
An immutable, content-hashed snapshot of an ETL Script. Pipeline Bindings pin a
version (or "latest"), so every ETL Job is reproducible.

### Pipeline Binding
The link, within a Research Project, between an ETL Datatype, a source bucket
(with prefix/pattern), an ETL Script (version), a grouping mode (per file or
per folder), and a Raw Bucket destination.

### Raw Bucket
The bucket where source files are moved (copy, verify, then delete source) after
a successful ETL Job, nested under the Job's id. No opt-out: every successful
Job's inputs are moved. A source delete that keeps failing retries with capped
backoff, then escalates (staff/Admin/Data-Manager email + audit event) and
leaves the source in place for manual handling.

### ETL Job
One run of one Script Version over one group of input files. Records script
version, input object keys and checksums, runtime image digest, status, and log.
Loading is all-or-nothing per job.

A "running" Job past its Binding's sandbox timeout plus grace period is shown as
**stuck** until the orchestrator's stuck-job sweep fails it (and auto-retries it
if infra-class). "Stuck" is a displayed state, not a stored status.

### Manual Retry
A fresh ETL Job an Admin or Data Manager starts from a failed Job: same
Binding, same inputs, and the failed Job's own Script Version (not the
Binding's current one). It starts at attempt 1 and isn't linked as an
auto-retry. Refused while the Binding already has an active Job. Audited.

### Sandbox Runner
The isolated, ephemeral container in which custom ETL Scripts execute: no
network, read-only staged input, resource-limited, no credentials. Built-in
scripts run in-process.

## Decisions (ADRs)

| ADR | Title | Status |
|-----|-------|--------|
| 0001 | Use django-allauth SocialAccount for OIDC integration | Accepted |
| 0002 | Enable local email/password login in development | Accepted |
| 0003 | Use django-oauth-toolkit JWT support for API tokens | Accepted |
| 0004 | Implement sliding inactivity timeout for sessions | Accepted |
| 0005 | Extend AuditLog model for session audit logging | Accepted |
| 0006 | Single OIDC provider via environment variables | Accepted |
| 0007 | Discovery URL for OIDC provider endpoint configuration | Accepted |
| 0008 | Just-in-time provisioning with group-based access control | Accepted |
| 0009 | Database-stored role mapping with env-var seeding | Accepted |
| 0010 | 8h max session / 30min idle timeout; 90-day audit log retention | Accepted |
| 0011 | Env-var superuser creation + OIDC role-based superuser | Accepted |
| 0012 | Remove django_auth_adfs from dependencies | Accepted |
| 0013 | App-startup seeding + management command for role mappings | Accepted |
| 0014 | Generic SSO button with configurable display name | Accepted |
| 0015 | Unit tests for adapter/model + responses-mocked integration tests | Accepted |
| 0016 | MIRES_AUTHENTICATION_FRAMEWORK retains mode selector (local/oidc/adfs/yubikey) | Accepted |
| 0017 | YubiKey/WebAuthn MFA as combinable second factor with OIDC | Accepted |
| 0018 | Data Collection Goal as a multi-valued, metric-typed, optionally site-scoped concept | Accepted |
| 0019 | Explicit Project Site linkage and many-valued Site Assignment | Accepted |
| 0020 | Chart API response envelope: Config/Data split, per-Grouping labels, always-array Groupings | Accepted |
| 0021 | Chart Event Callback resolution: client-side registry, lazy fire-time lookup | Accepted |
| 0022 | Chart Palette: fixed categorical set, brand-anchoring rejected; live-derived sequential ramp | Accepted |
| 0023 | Chart Grid: combined dataUrl, shared per-type trace-builder functions, subplot-attributed events | Accepted |
| 0024 | Data-access audit events kept 10 years, separate from 90-day auth-event retention | Accepted |
| 0025 | ETL orchestrator: SandboxBackend.run() stays blocking, no async start/poll split | Accepted |
| 0026 | Viewer-made Annotations and Segmentations stored as re-ingested DICOM objects, with Blinded Annotation | Accepted |
| 0027 | Machine clients bound to one project; Project Admins may grant raw DICOM access | Accepted |
| 0028 | De-identification Profile: PS3.15 Basic with retention options, fixed system-wide | Accepted |

### ADR 0028 — De-identification Profile: PS3.15 Basic with retention options, fixed system-wide

**Context**: The shared sanitizer, used by the ingestion metadata dump and by
WADO-RS at serve time, stripped only 19 hand-picked tags. That left 153 PS3.15
Basic Profile gaps (AccessionNumber, OriginalAttributesSequence,
IconImageSequence, observer names, …), every private tag, and 45 unrewritten
UID tags (wayfinder map: DICOM viewer web component — design spec, issue #176;
research #204, decided in #205). The viewer needs SUV inputs, spacing,
series descriptions and cross-object UID references. The alternatives were
keeping the 19-tag list, strict Basic with date shifting, or a profile chosen
per project.

**Decision**: One fixed De-identification Profile, driven by the PS3.15
Table E.1-1 data: Basic Profile + Retain Patient Characteristics + Retain
Longitudinal Temporal Information with Full Dates + Retain Device Identity +
Retain Institution Identity + Retain Safe Private, plus a local exception for
GE (0009,xx0D) (`GEMS_PETD_01`) post-injection datetime. Every instance UID
in E.1-1 is rewritten with the per-project HashUID; class and transfer-syntax
UIDs aren't. PatientName and PatientID are replaced with the Study
Participant's pseudonym. A fixed allowlist of structural descriptors
(Study/Series Description, ProtocolName, BodyPartExamined) is kept as-is and
other free-text descriptors are removed. Served headers carry
`PatientIdentityRemoved=YES` and `DeidentificationMethod` plus codes for only
the options actually applied, and the text notes the descriptor deviation.
The same profile applies to the metadata dump, and a backfill task
re-sanitizes existing dumps. The viewer flags series with burned-in
annotation (`BurnedInAnnotation=YES`, or missing on SC/US) and doesn't
scrub pixels.

**Consequences**:
- Full dates rather than shifted dates: the app already stores and shows
  real study dates, so a shift applied only when serving would put the
  viewer out of step with the app and protect almost nothing. Date shifting
  would have to be a decision for the whole app.
- Keeping descriptors without cleaning them isn't Clean Descriptors
  conformance. That residual risk is accepted because the series list needs
  them.
- Rewriting every UID keeps SEG/SR references to their source images
  resolvable once the source UIDs are pseudonyms.
- The raw-bytes endpoints (`dicom:raw`, ADR 0027) still return the original
  files. The profile governs `read` only.
- Supersedes decision 3 of the WADO-RS ticket (#190): "reuse
  `PHI_TAG_KEYWORDS` exactly".

### ADR 0027 — Machine clients bound to one project; Project Admins may grant raw DICOM access

**Context**: Machine-to-machine (client-credentials) callers of the WADO-RS
endpoints were gated only by the global `read` scope, with no Participant
Visibility check (wayfinder map: DICOM viewer web component — design spec,
issue #176; decided in issue #203). The raw-bytes endpoints return the stored
files with their original UIDs and full PHI (#115). The alternatives were
leaving it as it was, a scope per project, or turning off M2M WADO.

**Decision**: Each client has a Client Binding to exactly one Research
Project, with an optional Site, and gets that Site's Participant Visibility on
WADO-RS; an unbound client gets 404. Under Blinded Annotation, bound clients
get 404 on Annotation and Segmentation series. The raw-bytes endpoints need a
new `dicom:raw` scope; `read` alone gets only sanitized `/metadata` and
`/frames`. An Admin, or a Project Admin for their own project, issues,
rotates and revokes clients, picks the Site, and grants `read` and
`dicom:raw`; the bound project can't be changed. Clients belong to the
project and outlive the issuer's role.

**Consequences**:
- A Project Admin can release full PHI to a machine without an Admin. Every
  client change is audit-logged, and `dicom:raw` grants and revocations are
  data-access audit events (ADR 0024).
- Access is audited once per client, series and access token, whether it is
  metadata, frames or raw bytes.
- For now, only WADO-RS honours the binding; the other `read` endpoints stay
  global until a follow-up applies it.

### ADR 0026 — Viewer-made Annotations and Segmentations stored as re-ingested DICOM objects, with Blinded Annotation

**Context**: The DICOM viewer (wayfinder map: DICOM viewer web component —
design spec, issue #176; decided in issue #189) lets users create Annotations
and Segmentations. The alternatives were Cornerstone JSON (lossless in the
viewer but tied to it, with no interoperability), a new model holding the
bytes, or standard DICOM derived objects (research in issue #188).
Inter-rater studies also need raters who cannot see each other's work.

**Decision**: The browser builds SR (TID 1500) and SEG (BINARY) objects with
the Cornerstone adapters. The server sanitizes them, rewrites UIDs and
patient/study tags from the database, and ingests them as ordinary Dicom
Series in the source Dicom Study. ANN is built server-side with highdicom.
A provenance record per object holds its author (none if ingested), its
source series (many, same Frame of Reference), its predecessor, and whether
it is retired. Objects never change: Supersede makes a new version in one
linear chain, and a save on a stale head is rejected. Retire replaces delete.
Drafts live only in the browser (IndexedDB). A per-project Blinded Annotation
flag limits every user to their own work. A PI, Site PI or Admin can override
it with a per-participant, per-session Blinding Reveal, which is audit logged.

**Consequences**:
- WADO-RS, Participant Visibility and the viewer serve Annotations and
  Segmentations with no extra code. The Annotation and Segmentation Data
  Kinds are split out of Dicom Series by modality (SR/ANN vs SEG/RTSTRUCT)
  and count only the head of each chain.
- Browser-built objects must never be trusted: they go through the same
  sanitizer as ingestion.
- Create, Supersede, Retire, Blinding Reveal and blinding-flag changes are
  data-access audit events (ADR 0024).

### ADR 0025 — ETL orchestrator: SandboxBackend.run() stays blocking, no async start/poll split

**Context**: The ETL orchestrator (#162) runs each Job's sandbox execution inside a single
`QUEUE_ETL_RUN` Celery task, calling `SandboxBackend.run()` and waiting for it to return --
blocking that task for up to the Binding's resolved sandbox timeout (10 minutes by default). An
async alternative -- splitting `SandboxBackend` into a `start()` plus a separate poll-for-status
task -- was named and explicitly deferred during the pipeline's spec (issue #156, decision #146).

**Decision**: `run()` stays synchronous and blocking within its own Celery task. A task that never
returns (worker crash, node eviction) is recovered by a separate timeout-plus-grace sweep
(`recover_stuck_etl_jobs`), not by the run task reporting its own heartbeat.

**Consequences**:
- A `QUEUE_ETL_RUN` worker is occupied for the whole sandbox run; the queue's own worker
  concurrency, not this task, bounds how many Jobs run at once.
- Revisiting this toward an async start/poll split would reopen #146 (Sandbox runner spec) and
  change the `SandboxBackend` interface itself, not just the orchestrator.

### ADR 0024 — Data-access audit events kept 10 years, separate from 90-day auth-event retention

**Context**: ADR 0010 set a single 90-day retention for the Audit Log, which
then held only authentication events. The Data panel (wayfinder map: Project
Data panel — design spec, issue #175; decided in issue #181) adds
data-access events: participant data view opens, viewer opens, WADO fetches,
PROM Signing, PROM re-linking and Identity Reveal. Questions about who looked
at a participant's health data or identity arise long after 90 days.

**Decision**: Data-access events stay in the same `AuditLog` table but are
purged on their own setting, `DATA_ACCESS_AUDIT_RETENTION_DAYS`, which
defaults to 10 years. Authentication events keep `AUDIT_LOG_RETENTION_DAYS`
(90 days).

**Consequences**:
- `purge_old_audit_logs` must apply retention per event-type group.
- The table grows with data access. WADO fetches are logged once per
  session and series to bound volume, and denied fetches are always logged.

### ADR 0023 — Chart Grid: combined dataUrl, shared per-type trace-builder functions, subplot-attributed events

**Context**: The charting web components effort (wayfinder map: Charting web
components (Plotly.js) + serializers: architecture & API contract spec,
issue #75) needs to support mixed-type subplots — e.g. a bar chart beside a
line chart in one figure. plotly.js only composes subplots within one
figure/DOM node (its own native `grid` layout), so this can't be built by
mounting several of the already-specified per-type elements (#77–#84) side by
side; one new wrapper element has to build one Plotly figure from a mix of
types. Three sub-decisions followed from that: how the wrapper fetches data
for potentially several unrelated-looking subplots at once; how it builds
each subplot's traces without duplicating the trace-construction logic
already specified per type; and how a click/zoom event — which the base
class (#76) normally attributes to "the one chart type this element is" —
gets attributed to whichever specific subplot the user actually interacted
with.

**Decision**: `<mires-chart-grid>` fetches **one combined `dataUrl`**,
reusing the standard envelope from #74 unchanged
(`{config, groupings: [...]}`) — `config` carries the fixed grid layout
(`rows`, `cols`, and an ordered `subplots: [{type, row, col, config?}]`
list), and each Grouping's `data.subplots` carries one entry per subplot,
shaped exactly like that subplot type's own standalone Chart Data. One
Grouping dropdown drives every subplot in lockstep, matching Chart
Grouping's existing meaning ("switch between related views of the same
dataset"). Each of #77–#84's `buildTraces` method is refactored into an
**exported pure function** (e.g. `buildBarTraces(data, config)`) that the
standalone element's `buildTraces` now just calls — the grid wrapper imports
and calls the same functions, keyed by `type`, so there is exactly one
implementation of each chart type's trace-construction logic, never two
copies that can drift. The base class's event-firing method (#76) gains an
optional context-override parameter so a subclass can attribute a fired
event to something other than its own single `chartType`; the grid overrides
it to resolve which subplot a Plotly click/relayout event actually landed on
and enriches the normalized callback payload with that subplot's own type
before delegating to the shared registry-resolution logic from #73.

**Consequences**:
- #77–#84 are amended: each ships an exported pure trace-builder function
  alongside its Lit element, not trace-building logic embedded only inside
  the element's method body.
- #76 is amended a second time (after #78's `extraLayout` addition): its
  event-firing method takes an optional override so grid-style wrappers can
  attribute events correctly; the single-chart case is unaffected (no
  override supplied, behavior unchanged).
- A mixed-subplot chart cannot mix Chart Groupings across its subplots — if
  two subplots need genuinely independent grouping selection, they belong in
  two separate chart instances, not one Chart Grid.
- Non-axis chart types (pie, sankey) are positioned within the grid via
  Plotly's `domain` fractions rather than shared `xaxis`/`yaxis` references,
  since they have no axes to assign.
- A trace-builder function that needs resolved Chart Palette colors (heatmap,
  sankey) takes them as a parameter rather than calling `getComputedStyle`
  itself, so the function stays a pure mapping from data+config(+colors) to
  Plotly traces regardless of which element — standalone or grid — is
  calling it.

### ADR 0022 — Chart Palette: fixed categorical set, brand-anchoring rejected; live-derived sequential ramp

**Context**: The charting web components effort (wayfinder map: Charting web
components (Plotly.js) + serializers: architecture & API contract spec,
issue #71) needs a default color/typography scheme derived from MiqaResearch's
existing CSS custom properties, since plotly.js cannot read CSS variables
natively. MiqaResearch's brand is only two HSL hues
(`--mires-color-primary-parts`, a violet, and `--mires-color-secondary-parts`,
a blue) — not enough to safely produce an 8-series categorical palette by
formula. The `dataviz` skill's method requires a categorical palette to pass
six checks (lightness band, chroma floor, colorblind-vision separation,
contrast, a fixed documented set) that are calibrated to *specific* validated
hue/lightness combinations, not to arbitrary runtime hues. To test whether
MiqaResearch's own brand hues could be worked into the categorical set's
opening slots, the skill's own `validate_palette.js` was run against a
brand-anchored reordering placing primary (violet) and secondary (blue)
adjacent to each other: it **failed** the dark-mode normal-vision floor
(ΔE 9.8, below the 15 floor) and the CVD check (ΔE 1.9) — the two brand hues
are simply too close once stepped for the dark surface.

**Decision**: The categorical colorway ships as the `dataviz` skill's own
documented 8-hue default, **unmodified** (`--mires-chart-series-1` through
`-8`, individually overridable per site, each defaulting to the skill's
validated hex value) — already proven to clear every gate in both light and
dark mode, and its slot 1 (blue) and slot 7 (violet) happen to already sit in
MiqaResearch's brand hue families, so no further brand-matching work was
judged worth the risk of re-breaking a validated set. The sequential ramp
(heatmap, 2D density — magnitude, not identity) is the opposite case:
computed **live** from `--mires-color-primary-parts` via CSS relative-color
syntax (matching the existing `--mires-color-background-darker` pattern
already in `styles.ts`) at six fixed lightness steps
(`--mires-chart-sequential-0` through `-5`), because a single-hue lightness
ramp only needs monotonicity, not pairwise colorblind separation, so it *is*
safe to derive from an arbitrary brand hue. Background, text, and font
continue to come directly from the existing `--mires-color-background`,
`--mires-form-color-text`, and `--form-font-family` variables — no new
variables needed there.

**Amendment (from #82)**: A third, **diverging** ramp was added —
`--mires-chart-diverging-negative`/`-neutral`/`-positive`, a fixed
blue↔gray↔red set per the `dataviz` skill's diverging-pair guidance, not
derived from any brand hue (same reasoning as the categorical set: polarity
color needs specific validated hue pairing, not an arbitrary runtime hue).
Heatmap (#82) is the first type to use it, opting in per-chart via
`config.colorScale: "sequential" | "diverging"` for data with a meaningful
zero (e.g. a correlation matrix), where the single-hue sequential ramp would
hide which side of zero a cell falls on.

**Amendment (from #84)**: Sankey is a **documented exception** to the
"colors always come from the fixed palette, no per-item override" rule
established for XY series (#77) and pie slices (#80). A Sankey's node count
is open-ended — routinely beyond the categorical set's 8 safe slots — so
per-node identity was never the case the categorical-palette restriction was
protecting (a small, fixed number of overlaid series). `SankeyNode.color`
and `SankeyLink.color` are therefore optional explicit overrides: a node
without one defaults to a neutral tone, a link without one defaults to a
translucent tint of its source node's resolved color (the standard Sankey
convention for making flow direction traceable).

**Consequences**:
- A site that wants closer brand-matched categorical colors must override the
  8 `--mires-chart-series-*` variables individually and re-validate its own
  choice with the `dataviz` skill's script — the chart components do not
  attempt to auto-derive or auto-validate a categorical palette from
  whatever hues a site sets.
- If a future site's rebrand makes the stock categorical hues feel visually
  off, revisiting this means re-running the skill's enumeration-and-validate
  procedure by hand — not a quick formula change — because reordering or
  re-stepping is exactly what already failed once here.
- The sequential ramp automatically follows a site's primary hue with zero
  extra configuration, unlike the categorical set.
- Chart components must resolve all of these via `getComputedStyle` at
  render time (and again on the OS/`data-theme` re-theming triggers decided
  in this same ticket), since Plotly's layout/colorway config is a plain JS
  object, not something CSS can feed it directly.

### ADR 0021 — Chart Event Callback resolution: client-side registry, lazy fire-time lookup

**Context**: The charting web components effort (wayfinder map: Charting web
components (Plotly.js) + serializers: architecture & API contract spec) lets
a `dataUrl` API response name an external JS function to call on chart
click/zoom (`config.eventCallbacks`, locked by ADR 0020). Because that name
is server-supplied data, resolving it directly against the global scope
(`window[name]`) or via `eval` would let a compromised or malicious API
response execute arbitrary code already present on the page — a real,
if same-origin, trust-boundary concern (wayfinder issue #73). A registration
model needed a resolution-timing answer too: registering before a component
merely *renders* is a stricter, more failure-prone requirement than
registering before the user actually *interacts* with it.

**Decision**: Chart Event Callbacks resolve only against an explicit,
client-side registry — `window.mires.registerChartCallback(name, fn)`
(also exported as a module function from the charts bundle for consumers who
import it) — never a raw global-scope lookup. Resolution is lazy: a
component looks the name up in the registry only at the moment a
`plotly_click` or `plotly_relayout` event actually fires, not at
connect-time or data-fetch time, so the host page only needs to have
registered the name before the user interacts, not before the chart first
renders — eliminating most script-load-order races without needing a
"wait for late registration" mechanism. An unresolved name logs one
`console.warn` and no-ops; it never throws, so a misconfigured or optional
callback degrades gracefully instead of breaking the chart's data display.
Zoom is backed by `plotly_relayout` only (which already covers
double-click-to-reset-axes); legend clicks are excluded from both "click"
and "zoom". The callback receives a normalized `{chartId, chartType,
groupingName, event, raw}` payload rather than the bare Plotly event, with
`raw` kept as an escape hatch for callback authors who need the underlying
Plotly event data.

**Consequences**:
- A malicious or buggy API response can at worst name a callback nobody
  registered (harmless no-op) or one the host page already explicitly chose
  to expose — it can never make the browser run code the page didn't opt
  into. This is the load-bearing security property of the whole mechanism.
- The shared base class (wayfinder ticket #76) must guard its own
  `Plotly.Plots.resize()` calls (used for container-resize responsiveness)
  so they don't also trigger the registered "zoom" callback — a
  component-internal reflow is not a user zoom.
- Callback authors write against the normalized payload shape for the common
  case (which chart, which Grouping, which event) without needing to learn
  Plotly's raw event shapes, while `raw` still supports advanced use.
- Because resolution happens at event-fire time rather than connect-time,
  there is no compile-time or connect-time way to catch a typo'd callback
  name — the `console.warn` at first fire is the only signal.

### ADR 0020 — Chart API response envelope: Config/Data split, per-Grouping labels, always-array Groupings

**Context**: The charting web components effort (wayfinder map: Charting web
components (Plotly.js) + serializers: architecture & API contract spec) needs
one JSON contract that every `dataUrl` endpoint returns, consumed by both the
shared Lit base class (wayfinder ticket #76) and 8 chart-type-specific
serializer tickets (#77–#84). Three shapes were genuinely open: whether a
chart with only one Chart Grouping gets a simplified top-level response or the
same shape as a multi-Grouping one; whether axis/legend titles are fixed for
a whole response or can vary per Grouping; and how the WebGL Threshold
override is expressed now that research (issue #72) confirmed only 4 of 11
chart types have a WebGL-accelerated trace at all.

**Decision**: The response envelope is always `{config, groupings}`, where
`groupings` is a non-empty array even when there is exactly one Grouping (the
component simply skips rendering the dropdown at `groupings.length === 1`) —
one parsing path, no distinct single-Grouping shape. Chart Config carries
what's fixed across every Grouping in a response: `webglThreshold` (default
100) plus a `forceRenderer: "svg" | "webgl" | "auto"` escape hatch,
`eventCallbacks: {click?, zoom?}` (Chart Event Callback names — resolution
mechanism is wayfinder ticket #73), and the mixed-subplot layout (internals
deferred to ticket #75). Chart Data — the per-Grouping trace values — may
also carry an optional `labels` sub-object (`xAxisTitle`, `yAxisTitle`,
`legendTitle`, `xAxisRange`, `yAxisRange`) that overrides Config's defaults,
because switching Grouping can change what's being measured, not only how
it's sliced; `xAxisRange`/`yAxisRange` override Plotly's computed autorange
only when set (either element may be `null` to pin just that end while the
other stays autoranged, per Plotly's own `range` semantics), otherwise
autorange behaves as before. On the Django
side, schema fields stay idiomatic Python snake_case
(`webgl_threshold`, `event_callbacks`, `x_axis_title`, …).

**Amendment (found while writing the handoff spec, before any code
existed)**: this ADR originally specified Django REST Framework
(`serializers.Serializer`) plus a shared camelCase-rendering mixin
("djangorestframework-camel-case") converting to/from camelCase at the wire
boundary. Neither matches this codebase: every existing serializer module
(`MiqaResearch/data/serializers/participant_consent.py`) already uses
**django-ninja's `Schema`** (Pydantic-based), and **no endpoint anywhere
renders camelCase** — wire format is plain snake_case JSON throughout the
app. Corrected: chart schemas are `ninja.Schema` classes, wire format is
plain snake_case matching every other endpoint, and the Lit base class
(`MiresChartBase`) does one small snake_case→camelCase key conversion when
it parses a fetched response, so TS-side field names stay camelCase
internally without the wire format needing to be. The envelope shape itself
(`{config, groupings}`, the Config/Data split, always-array Groupings) is
unaffected by this correction.

**Consequences**:
- Every chart-type schema parametrizes a shared generic
  `ChartResponseSchema[TData]` / `ChartGroupingSchema[TData]` base (Pydantic
  generics — analogous to the shared Lit base class) with its own Data
  schema, and overrides `config` only when it has its own Config fields —
  see the handoff spec (`docs/charts-handoff.md`) for the full schema
  hierarchy.
- A chart type with no WebGL trace (7 of 11, per issue #72) still exposes
  `webglThreshold`/`forceRenderer` on its Config; the base class documents
  this as a no-op rather than omitting the fields, keeping one consistent
  Config shape across all 11 components.
- Because `labels` lives on Chart Data, a Grouping switch can change axis
  titles without a distinct API shape for that case — the base class must
  apply `labels` (if present) on every Grouping-switch render, not only on
  initial load.
- Wayfinder tickets #75 (mixed-subplot component shape) and #76 (shared base
  class) consume this envelope directly; the 8 per-chart-type tickets
  (#77–#84) define what goes inside each `data` object.

### ADR 0019 — Explicit Project Site linkage and many-valued Site Assignment

**Context**: The Dashboard feature needs to know which Sites (clinics)
participate in a Research Project, and which Site a given User should see
status for. Today, `Clinic` is a global, unscoped model created ad-hoc
whenever consent data is imported (`participant_consents.py`); nothing links
a `Clinic` to a `ResearchProject`, and nothing links a `User` to a `Clinic` at
all. Two shapes were considered for the project-to-site relationship: infer it
from whatever `Clinic` values already appear on the project's
`ParticipantConsent` records, or make it an explicit, admin-configured link.

**Decision**: A Research Project's Sites are explicit (**Project Site**), not
inferred from consent data — an Admin or PI configures which Sites
participate in a project independent of whether any consent data referencing
that Site exists yet, because real multi-site studies agree on their sites
before data collection starts. A project is **multi-site** exactly when it
has more than one Project Site.

Separately, **Site Assignment** (User × Research Project × Site) is
many-valued: a User can hold assignments to more than one Site on the same
project, rather than being limited to one. Assignment applies uniformly
regardless of `ResearchProjectRole` — no role is restricted from holding one.
Only Admin and PI may create or edit Site Assignments, mirroring Data
Collection Goal's edit rights (ADR 0018). A User with zero Site Assignments
sees project-level dashboard information only; a User with one or more sees
every assigned Site's status alongside the project-wide view, not just one
"primary" site.

**Consequences**:
- Setting up a multi-site project now requires an explicit admin step
  (configuring its Project Sites) before Goals or Site Assignments can
  reference a Site — there's no automatic bootstrapping from uploaded data.
- The admin UI (ticket #25) needs two related but distinct forms: configuring
  a project's Project Sites, and assigning Users to Sites.
- The Goals tab (ticket #24) must be able to render more than one assigned
  Site's status for a single User, not just one.
- `Clinic` itself is unchanged and stays a global, unscoped model; only its
  participation in a given project is now tracked explicitly via Project
  Site.

### ADR 0018 — Data Collection Goal as a multi-valued, metric-typed, optionally site-scoped concept

**Context**: The Dashboard feature (wayfinder map: Dashboard feature spec) needs
a way to show a Research Project's data-gathering progress. The obvious minimal
shape — one target number per project — didn't survive contact with the actual
requirement: research projects here track progress along genuinely different
axes (consent for a specific form, raw enrollment, and imaging completeness
against `DicomStudy`/`DicomSeries`), and a multi-site project needs to see both
its overall standing and its own site's standing side by side.

**Decision**: A Research Project may define **zero or more** Data Collection
Goals rather than exactly one. Each Goal independently picks a metric type —
participants holding a specific `ParticipantConsentType`, raw enrolled
`StudyParticipant` count, or participants with a configured set of DICOM
modalities present (with the goal choosing ALL-required vs. ANY-suffices
matching, checked across any of the participant's `DicomStudy` records) — and
may optionally scope itself to a single Site instead of the whole project.
A Goal may also carry an explicit start date and target date (both optional,
independent); only when both are present does status include an on-track/
behind-schedule pace judgment, otherwise status is plain percent-complete. The
start date is explicit rather than inferred, because neither `ResearchProject`
nor `StudyParticipant` carries a creation timestamp in this codebase today.
Only the Admin and PI project roles may create or edit Goals.

**Consequences**:
- The study-picker card can no longer name "the" goal — with an unbounded
  number of Goals per project, the card shows an aggregate rollup (e.g. "2 of
  3 goals on track") instead of one goal's progress.
- The Goals tab renders as a list, one row per Goal, rather than a single
  status block.
- The Goals tab now depends on the imaging pipeline (`DicomStudy`,
  `DicomSeries`) in addition to consent data — a broader dependency than its
  original "consent progress" framing.
- Pace status (on-track/behind) is opt-in per Goal and silently absent
  whenever an Admin/PI leaves the start date blank.

**Amendment (wayfinder ticket #25)**: A DICOM modality-set Goal additionally
picks how it **counts**: **participants** (the original behavior above —
one count per distinct `StudyParticipant`, however many qualifying
`DicomStudy` records they have, matched across any of that participant's
studies) or **imaging sets** — counting each qualifying `DicomStudy`
separately, so a participant with several qualifying studies contributes
several toward the target rather than one. Under imaging-set counting, "one
set" requires the modalities to co-occur within a single `DicomStudy`; the
original scattering-across-studies allowance only applies to participant
counting. The ALL-required/ANY-suffices matching choice applies unchanged
under either counting mode.
- Site scoping lives on Goal itself; the sibling Site & Site Assignment
  design only needs to define what a Site is, not how goals attach to one.

### ADR 0017 — YubiKey/WebAuthn MFA as combinable second factor with OIDC

**Context**: The original `MIRES_AUTHENTICATION_FRAMEWORK` defaulted to `"yubikey"`,
which did not match any code branch in `settings.py` and was effectively a no-op.
The login page template (`login.partial.html`) already has a YubiKey/Passkey
section linking to allauth's `mfa_reauthenticate` URL.

**Decision**: The `"yubikey"` mode is retained as a valid authentication framework
mode alongside `"local"`, `"oidc"`, and `"adfs"`. It enables WebAuthn/passkey
authentication via django-allauth's MFA module. Unlike the other modes,
`"yubikey"` can be **combined** with `"oidc"` or `"adfs"` to provide two-factor
authentication (OIDC as first factor, WebAuthn as second). The mode is selected
via the `MIRES_AUTHENTICATION_FRAMEWORK` env var, which can accept a
comma-separated list (e.g., `"oidc,yubikey"`) to enable multiple modes
simultaneously.

**Consequences**:
- The login page dynamically shows the YubiKey/Passkey section when `"yubikey"`
  is among the active modes.
- In production, operators can set `MIRES_AUTHENTICATION_FRAMEWORK=oidc,yubikey`
  to require both OIDC login and WebAuthn verification.
- The `MFA_PASSKEY_LOGIN_ENABLED` setting controls whether passkeys can be used
  as a standalone login method (not just as a second factor after password).
- This preserves the existing login page template structure while adding
  conditional rendering based on the active authentication modes.
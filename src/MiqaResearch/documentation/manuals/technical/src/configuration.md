(heading-configuration)=
# Configuration

MIQA Research is configured entirely through environment variables. All variables are
prefixed with `MIRES_` and are read at process startup by
{file}`MiqaResearch/settings.py` using [django-environ](https://django-environ.readthedocs.io/).

Every variable can be set either as a real operating system environment variable (for
example, in a `docker-compose.yml` file) or through a `.env` file placed at the root of
the project. If both are present, an actual environment variable takes precedence over
the value in `.env`.

Most variables have a sensible default for local development and can be omitted. Variables
without a default are noted below; the application will fail to start if a required
variable is missing.

:::{note}
Some settings — most notably data-encryption keys and the participant-consent service
credentials — can alternatively be resolved from a running [HashiCorp
Vault](https://www.vaultproject.io/) instance instead of being set directly as
environment variables. See [Secrets and data encryption](#heading-configuration-secrets)
and [Participant consent](#heading-configuration-consent) below.
:::

## Core application settings

General settings that control how the Django application itself runs.

| Variable | Default | Description |
|---|---|---|
| `MIRES_SECRET_KEY` | *(required)* | Django's cryptographic signing key. Must be kept secret and unique per environment. |
| `MIRES_DEBUG` | `False` | Enables Django debug mode. Also relaxes several security settings — see [Security-sensitive behaviour of DEBUG](#heading-configuration-debug). Never enable in production. |
| `MIRES_BASEURL` | `http://localhost:8000` | The externally reachable base URL of the application. |
| `MIRES_ALLOWED_HOSTS` | *(none)* | Comma-separated list of hostnames the application is allowed to serve, e.g. `mires.example.org,mires-internal.example.org`. Maps to Django's `ALLOWED_HOSTS`. |
| `MIRES_CSRF_TRUSTED_ORIGINS` | *(none)* | Comma-separated list of origins trusted for cross-site CSRF-protected requests, e.g. `https://mires.example.org`. |
| `MIRES_CORS_ALLOWED_ORIGINS` | `http://localhost:8000` | Comma-separated list of origins allowed to make cross-origin requests to the API. |
| `MIRES_ADMIN_URL` | `miresadm` | The URL path segment under which the Django admin site is served. Change this to avoid exposing the admin under a predictable path. |
| `MIRES_STATIC_URL` | `/static/` | URL prefix used to serve static assets. |
| `MIRES_STATIC_ROOT` | `<project>/static_root` | Filesystem path collected static files are written to by `collectstatic`. |
| `MIRES_MEDIA_ROOT` | `<project>/media` | Filesystem path where uploaded media files are stored. |

(heading-configuration-debug)=
:::{warning}
When `MIRES_DEBUG` is enabled, the Django Debug Toolbar is loaded, session cookies are
allowed over plain HTTP, the WebAuthn origin check is relaxed, and the
`SessionTimeoutMiddleware` (see [Sessions and audit logging](#heading-configuration-sessions))
is skipped entirely. Only enable it in local development.
:::

## Sessions and audit logging

(heading-configuration-sessions)=

| Variable | Default | Description |
|---|---|---|
| `MIRES_SESSION_COOKIE_AGE` | `28800` (8 hours) | Absolute maximum lifetime of a session, in seconds, measured from login. |
| `MIRES_SESSION_IDLE_TIMEOUT` | `1800` (30 minutes) | Sliding idle timeout, in seconds. A session is logged out if no activity is seen within this window. |
| `MIRES_AUDIT_LOG_RETENTION_DAYS` | `90` | Number of days audit log entries are retained before becoming eligible for cleanup. |

Both the absolute and idle timeouts are enforced together, so a long-lived but idle
session is logged out even if it has not yet reached its absolute maximum lifetime.
Timeout enforcement is skipped while `MIRES_DEBUG` is enabled.

## Authentication

MIQA Research supports several login methods, selected and combined via
`MIRES_AUTHENTICATION_FRAMEWORK`.

| Variable | Default | Description |
|---|---|---|
| `MIRES_AUTHENTICATION_FRAMEWORK` | `yubikey` | Comma-separated list of enabled authentication modes. Recognised values: `yubikey` (WebAuthn passkey login), `oidc` (generic OpenID Connect), `adfs` (Active Directory Federation Services via OIDC), `siths`, `bankid` (Swedish e-identification methods). |

Enabling `oidc` or `adfs` activates a shared OpenID Connect login flow, configured by:

| Variable | Default | Description |
|---|---|---|
| `MIRES_OIDC_DISCOVERY_URL` | *(none)* | OIDC discovery document URL. Required when `oidc` is enabled (ignored when `adfs` is used instead). |
| `MIRES_ADFS_AUTHORITY` | *(none)* | Base URL of the ADFS authority, e.g. `https://adfs.example.org`. Required when `adfs` is enabled; the discovery URL is derived from it automatically. |
| `MIRES_OIDC_CLIENT_ID` | *(none)* | OAuth2 client ID registered with the identity provider. |
| `MIRES_OIDC_CLIENT_SECRET` | *(none)* | OAuth2 client secret registered with the identity provider. |
| `MIRES_OIDC_PROVIDER_DISPLAY_NAME` | `SSO` | Label shown on the login button. |
| `MIRES_OIDC_ROLES_CLAIM` | `role` | Name of the claim in the ID token used to map external roles onto local groups. |

E-identification (e-ID) login is configured separately:

| Variable | Default | Description |
|---|---|---|
| `MIRES_EID_CLIENT_ID` | *(none)* | Client ID for the e-identification provider. |
| `MIRES_EID_CLIENT_SECRET` | *(none)* | Client secret for the e-identification provider. |

## Database

MIQA Research uses PostgreSQL in production and falls back to a local SQLite database
file when no database host is configured, which is convenient for local development.

| Variable | Default | Description |
|---|---|---|
| `MIRES_DATABASE_URL` | *(none)* | Full database URL, e.g. `psql://user:password@host:5432/dbname`. When set, it takes precedence over the individual `MIRES_DB_*` variables below. |
| `MIRES_DB_ENGINE` | `django.db.backends.postgresql` | Django database backend to use. |
| `MIRES_DB_HOST` | *(none)* | Database host. If unset (and `MIRES_DATABASE_URL` is also unset), a local SQLite file at `db.sqlite3` is used instead. |
| `MIRES_DB_DATABASE` | `tanqa` | Database name. |
| `MIRES_DB_USER` | *(none)* | Database user. |
| `MIRES_DB_PASSWORD` | *(none)* | Database password. |
| `MIRES_DB_PORT` | *(none)* | Database port. |
| `MIRES_DB_SSL_MODE` | *(none)* | SSL mode used for the database connection, when required by the database host. |

## Caching

| Variable | Default | Description |
|---|---|---|
| `MIRES_CACHE_BACKEND` | `django.core.cache.backends.db.DatabaseCache` | Django cache backend class. |
| `MIRES_CACHE_LOCATION` | `miqa_research_cache` | Backend-specific cache location, e.g. the database table name for the database cache backend. |
| `MIRES_CACHE_TTL` | `300` | Default cache entry lifetime, in seconds. |

When using the default database-backed cache, the cache table must be created with
`manage.py createcachetable` before first use.

## Email

| Variable | Default | Description |
|---|---|---|
| `MIRES_EMAIL_BACKEND` | `django.core.mail.backends.smtp.EmailBackend` | Django email backend class. Set to `django.core.mail.backends.console.EmailBackend` to print emails to the console instead of sending them, which is useful in local development. |
| `MIRES_EMAIL_HOST` | *(none)* | SMTP server hostname. |
| `MIRES_EMAIL_PORT` | `1234` | SMTP server port. |
| `MIRES_EMAIL_HOST_USER` | *(none)* | SMTP authentication username. |
| `MIRES_EMAIL_HOST_PASSWORD` | *(none)* | SMTP authentication password. |
| `MIRES_EMAIL_USE_TLS` | `True` | Whether to use TLS when connecting to the SMTP server. |
| `MIRES_EMAIL_NOREPLY_SENDER` | `noreply@miqaresearch.se` | Sender address used for outgoing system emails. |

## Logging

| Variable | Default | Description |
|---|---|---|
| `MIRES_LOGGING_LEVEL` | `INFO` | Root logging level, e.g. `DEBUG`, `INFO`, `WARNING`, `ERROR`. |
| `MIRES_LOGGING_DIR` | `<project>/LocalOnly/Logs` | Directory log files are written to. Created automatically at startup if it does not exist. |
| `MIRES_LOGFILE_PATH` | `<project>/LocalOnly/Logs/mires.log` | Reserved log file path. |

Log output is written both to the console and to a rotating log file
(`miqa_research.log` inside `MIRES_LOGGING_DIR`, capped at 5 MB with 5 backups kept).

The following variables configure export of logs to an OpenTelemetry (OTLP) collector:

| Variable | Default | Description |
|---|---|---|
| `MIRES_OTLP_ENDPOINT` | `http://localhost:4318/v1/logs` | OTLP collector endpoint that logs are exported to. |
| `MIRES_OTLP_PROTOCOL` | `http` | OTLP transport protocol. |
| `MIRES_OTLP_INSECURE` | `False` | Whether to allow an insecure (non-TLS) connection to the collector. |
| `MIRES_OTLP_SERVICE_NAME` | `miqa-research` | Service name reported to the collector. |

(heading-configuration-secrets)=
## Secrets and data encryption

Sensitive study data at rest is protected with a Fernet encryption key and a separate
hash key used for deterministic lookups. Both are always fetched from Vault at startup.

| Variable | Default | Description |
|---|---|---|
| `MIRES_VAULT_URL` | *(none)* | URL of the HashiCorp Vault instance, e.g. `http://localhost:8200`. |
| `MIRES_VAULT_TOKEN` | *(none)* | Vault authentication token. |
| `MIRES_DATA_HASH_KEY_VAULT_PATH` | `mires/datahashing` | Path of the KV v2 secret in Vault holding the `FernetKey` and `SensitiveDataHashKey` entries. |
| `MIRES_DATA_HASH_FERNET_KEY_ENCRYPTION` | `utf-8` | Text encoding used when decoding the Fernet key retrieved from Vault. |

## Task queue (Celery)

Background work — OCR processing, participant consent lookups, and scheduled tasks —
runs on Celery workers backed by RabbitMQ.

| Variable | Default | Description |
|---|---|---|
| `MIRES_CELERY_BROKER_URL` | `amqp://guest:guest@oqarabbit:5672//` | Connection URL of the RabbitMQ broker. |
| `MIRES_CELERY_RESULT_BACKEND` | `django-db` | Celery result backend. |
| `MIRES_CELERY_RESULT_EXTENDED` | `True` | Whether to store extended task metadata with results. |
| `MIRES_CELERY_TIMEZONE` | `Europe/Stockholm` | Timezone used for scheduling periodic (beat) tasks. |
| `MIRES_CELERY_TASK_TRACK_STARTED` | `True` | Whether tasks report a `STARTED` state when they begin executing. |
| `MIRES_CELERY_TASK_TIME_LIMIT` | `1800` (30 minutes) | Hard time limit for a single task, in seconds. |
| `MIRES_CELERY_WORKER_ENABLE_REMOTE_CONTROL` | `False` | Whether workers accept remote control commands (e.g. from Flower). |
| `MIRES_CELERY_WORKER_PREFETCH_MULTIPLIER` | `1` | Number of tasks a worker prefetches per queue slot. |

## OCR (Ollama)

Optical character recognition of uploaded PROM forms is performed by a local
[Ollama](https://ollama.com/) instance.

| Variable | Default | Description |
|---|---|---|
| `MIRES_OLLAMA_URL` | `http://localhost:11434` | Base URL of the Ollama API. |
| `MIRES_OLLAMA_MODEL` | `gemma4` | Name of the Ollama model used to perform OCR extraction. |

(heading-configuration-consent)=
## Participant consent

Settings controlling how the participant consent background task authenticates against
and reads consent records from an external source.

| Variable | Default | Description |
|---|---|---|
| `MIRES_TASK_CONSENT_SKIP_CLIENT` | `False` | When enabled, the consent client is not initialised and no credentials are resolved. Intended for workers that do not need to reach the consent source. |
| `MIRES_TASK_CONSENT_CLIENT_ID` | *(none)* | OAuth2 client ID used to authenticate against the consent source. If unset together with the client secret, both are instead resolved from Vault. |
| `MIRES_TASK_CONSENT_CLIENT_SECRET` | *(none)* | OAuth2 client secret used to authenticate against the consent source. |
| `MIRES_TASK_CONSENT_VAULT_PATH` | `mires/consent` | Vault KV v2 path holding the `ConsentClientId` and `ConsentClientSecret` entries, used as a fallback when the client ID/secret are not set directly. |
| `MIRES_TASK_CONSENT_ADFS_TOKEN_URL` | *(none)* | ADFS token endpoint used to obtain an access token for the consent source. |
| `MIRES_TASK_CONSENT_RESOURCE` | *(none)* | ADFS resource identifier requested for the consent source token. |
| `MIRES_TASK_CONSENT_BASE_URL` | *(none)* | Base URL of the consent source API. |
| `MIRES_TASK_CONSENT_SOURCE` | *(none)* | Identifier of the consent data source. |
| `MIRES_TASK_CONSENT_TIMEZONE` | `Europe/Stockholm` | Timezone consent timestamps are interpreted in. |

The consent source is expected to return tabular data whose column headers are
configurable, to accommodate different naming conventions in the source system:

| Variable | Default column name |
|---|---|
| `MIRES_TASK_CONSENT_FORM_COL_NAME` | `Namn` |
| `MIRES_TASK_CONSENT_FORM_COL_PID` | `Personnummer` |
| `MIRES_TASK_CONSENT_FORM_COL_STATUS` | `Status` |
| `MIRES_TASK_CONSENT_FORM_COL_SIGNED` | `Signerat` |
| `MIRES_TASK_CONSENT_FORM_COL_LAST_UPDATED` | `Senast Uppdaterad` |
| `MIRES_TASK_CONSENT_FORM_COL_RETRACTED` | `Återtaget` |
| `MIRES_TASK_CONSENT_FORM_COL_CLINIC` | `klinik` |
| `MIRES_TASK_CONSENT_FORM_COL_RESEARCH_PERSON_INFORMATION` | `fpi` |
| `MIRES_TASK_CONSENT_FORM_COL_READ_INFORMATION` | `Jag har läst och förstått "Information till forskningspersoner"` |
| `MIRES_TASK_CONSENT_FORM_COL_COMMENT` | `Kommentar` |
| `MIRES_TASK_CONSENT_FORM_COL_CONSENTED_TRUE_VALUES` | `Ja` |

`MIRES_TASK_CONSENT_FORM_COL_CONSENTED_TRUE_VALUES` accepts a comma-separated list of
values that should be interpreted as "consent given" when found in the status column.

## Initial data seeding

Applied once, the first time database migrations run.

| Variable | Default | Description |
|---|---|---|
| `MIRES_SU_EMAIL` | *(none)* | Email address for an initial Django superuser account. If unset, no superuser is created automatically. |
| `MIRES_SU_PASSWORD` | *(none)* | Password for the initial superuser account. |

:::{note}
When `MIRES_DEBUG` is enabled, a set of additional example users and a sample research
project are also created, to make the application usable immediately in a local
development environment.
:::

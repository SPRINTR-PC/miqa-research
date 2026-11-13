import json
from pathlib import Path

import environ

from contract.constants.celery import (
    QUEUE_CALCULATE_CONSENT_STATISTICS,
    QUEUE_DICOM_INGESTION,
    QUEUE_EMAIL,
    QUEUE_ETL_POLL,
    QUEUE_ETL_RUN,
    QUEUE_GET_CONSENTS,
    QUEUE_OCR,
)
from contract.constants.scopes import (
    SCOPE_ADMIN,
    SCOPE_DICOM_RAW,
    SCOPE_MONITOR_CLIENT,
    SCOPE_READ,
    SCOPE_UPSERT_CONSENT,
)
from helpers import vault
from helpers.vault import get_data_encryption_keys
from MiqaResearch.telemetry import otlp_logging_config

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    MIRES_ADMIN_URL=(str, "miresadm"),
    MIRES_ADFS_AUTHORITY=(str, None),
    MIRES_AUDIT_LOG_RETENTION_DAYS=(int, 90),
    MIRES_DATA_ACCESS_AUDIT_RETENTION_DAYS=(int, 3650),
    MIRES_AUTHENTICATION_FRAMEWORK=(str, "yubikey"),
    MIRES_DEBUG=(bool, False),
    MIRES_SECRET_KEY=(str, None),
    MIRES_STATIC_URL=(str, "/static/"),
    MIRES_STATIC_ROOT=(Path, BASE_DIR / "static_root"),
    MIRES_MEDIA_ROOT=(Path, BASE_DIR / "media"),
    MIRES_DATABASE_URL=(str, None),
    MIRES_DB_ENGINE=(str, "django.db.backends.postgresql"),
    MIRES_DB_HOST=(str, None),
    MIRES_DB_DATABASE=(str, "tanqa"),
    MIRES_DB_USER=(str, None),
    MIRES_DB_PASSWORD=(str, None),
    MIRES_DB_PORT=(str, None),
    MIRES_DB_SSL_MODE=(str, None),
    MIRES_LOGFILE_PATH=(Path, BASE_DIR / "LocalOnly/Logs/mires.log"),
    MIRES_BASEURL=(str, "http://localhost:8000"),
    MIRES_ALLOWED_HOSTS=(str, None),
    MIRES_CSRF_TRUSTED_ORIGINS=(str, None),
    MIRES_CORS_ALLOWED_ORIGINS=(str, "http://localhost:8000"),
    MIRES_CACHE_TTL=(int, 300),
    MIRES_CACHE_BACKEND=(str, "django.core.cache.backends.db.DatabaseCache"),
    MIRES_CACHE_LOCATION=(str, "miqa_research_cache"),
    MIRES_CELERY_BROKER_URL=(str, None),
    MIRES_CELERY_RESULT_BACKEND=(str, "django-db"),
    MIRES_CELERY_RESULT_EXTENDED=(bool, True),
    MIRES_CELERY_TIMEZONE=(str, "Europe/Stockholm"),
    MIRES_CELERY_TASK_TRACK_STARTED=(bool, True),
    MIRES_CELERY_TASK_TIME_LIMIT=(int, 30 * 60),
    MIRES_CELERY_WORKER_ENABLE_REMOTE_CONTROL=(bool, False),
    MIRES_CELERY_WORKER_PREFETCH_MULTIPLIER=(int, 1),
    MIRES_DATA_HASH_FERNET_KEY_ENCRYPTION=(str, "utf-8"),
    MIRES_DATA_HASH_KEY_VAULT_PATH=(str, "mires/datahashing"),
    MIRES_DICOM_S3_ENDPOINT_URL=(str, None),
    MIRES_DICOM_S3_REGION_NAME=(str, "us-east-1"),
    MIRES_DICOM_S3_ACCESS_KEY_ID=(str, None),
    MIRES_DICOM_S3_SECRET_ACCESS_KEY=(str, None),
    MIRES_DICOM_STORAGE_BACKEND=(str, "local"),
    MIRES_DICOM_S3_BUCKET=(str, None),
    MIRES_DICOM_MAX_PIXEL_DIMENSIONS=(int, 200_000),
    MIRES_DICOM_MAX_FRAME_COUNT=(int, 500_000),
    MIRES_DICOM_ORPHAN_DETECT_HOURS=(int, 2),
    MIRES_DICOM_ORPHAN_GRACE_HOURS=(int, 24),
    MIRES_DICOM_ORPHAN_MAX_DELETE_COUNT=(int, 100),
    MIRES_DICOM_ORPHAN_MAX_DELETE_FRACTION=(float, 0.05),
    MIRES_DICOM_ORPHAN_SWEEP_ACTION=(str, "delete"),
    MIRES_EMAIL_HOST=(str, None),
    MIRES_EMAIL_PORT=(int, 1234),
    MIRES_EMAIL_HOST_USER=(str, None),
    MIRES_EMAIL_HOST_PASSWORD=(str, None),
    MIRES_EMAIL_USE_TLS=(bool, True),
    MIRES_EMAIL_BACKEND=(str, "django.core.mail.backends.smtp.EmailBackend"),
    MIRES_EMAIL_NOREPLY_SENDER=(str, "noreply@miqaresearch.se"),
    MIRES_EID_CLIENT_ID=(str, None),
    MIRES_EID_CLIENT_SECRET=(str, None),
    MIRES_ETL_SCRIPT_S3_ENDPOINT_URL=(str, None),
    MIRES_ETL_SCRIPT_S3_REGION_NAME=(str, "us-east-1"),
    MIRES_ETL_SCRIPT_S3_ACCESS_KEY_ID=(str, None),
    MIRES_ETL_SCRIPT_S3_SECRET_ACCESS_KEY=(str, None),
    MIRES_ETL_SCRIPT_STORAGE_BACKEND=(str, "local"),
    MIRES_ETL_SCRIPT_S3_BUCKET=(str, None),
    MIRES_ETL_SCRIPT_MAX_SOURCE_BYTES=(int, 256 * 1024),
    MIRES_ETL_SCRIPT_IMAGE_KEYS=(str, '{".py": "python-etl-v1", ".r": "r-etl-v1"}'),
    MIRES_ETL_SYNC_NATIVE_SCRIPTS_ON_MIGRATE=(bool, True),
    MIRES_ETL_STORAGES=(str, "[]"),
    MIRES_SANDBOX_BACKEND=(str, "compose"),
    MIRES_SANDBOX_DOCKER_HOST=(str, "unix:///var/run/docker.sock"),
    MIRES_SANDBOX_COMPOSE_STORAGE_LIMIT=(bool, False),
    MIRES_ETL_SCRATCH_DIR=(str, ""),
    MIRES_ETL_SCRATCH_MARGIN_BYTES=(int, 256 * 1024 ** 2),
    MIRES_SANDBOX_IMAGE_ALLOWLIST=(str, "{}"),
    MIRES_SANDBOX_DEFAULT_TIMEOUT_SECONDS=(int, 10 * 60),
    MIRES_SANDBOX_DEFAULT_MEMORY_MB=(int, 1024),
    MIRES_SANDBOX_DEFAULT_CPU_MILLICORES=(int, 1000),
    MIRES_SANDBOX_DEFAULT_PIDS_LIMIT=(int, 128),
    MIRES_SANDBOX_MAX_INPUT_BYTES=(int, 15 * 1024 ** 3),
    MIRES_SANDBOX_MAX_OUTPUT_BYTES=(int, 1 * 1024 ** 3),
    MIRES_SANDBOX_K8S_NAMESPACE=(str, "mires-etl-sandbox"),
    MIRES_SANDBOX_K8S_STAGER_IMAGE=(str, "busybox:1.36"),
    MIRES_SANDBOX_K8S_SELF_TEST_TTL_SECONDS=(int, 300),
    MIRES_SANDBOX_K8S_EGRESS_PROBE_HOST=(str, "1.1.1.1"),
    MIRES_SANDBOX_K8S_EGRESS_PROBE_PORT=(int, 443),
    MIRES_ETL_S3_ENDPOINT_URL=(str, None),
    MIRES_ETL_S3_REGION_NAME=(str, "us-east-1"),
    MIRES_ETL_S3_ACCESS_KEY_ID=(str, None),
    MIRES_ETL_S3_SECRET_ACCESS_KEY=(str, None),
    MIRES_ETL_S3_VAULT_PATH=(str, "mires/etl-s3"),
    MIRES_ETL_POLL_INTERVAL_SECONDS=(int, 30),
    MIRES_ETL_LOG_RETENTION_DAYS=(int, 30),
    MIRES_ETL_JOB_MAX_AUTO_RETRIES=(int, 3),
    MIRES_ETL_JOB_STUCK_GRACE_SECONDS=(int, 300),
    MIRES_ETL_SOURCE_CLEANUP_MAX_ATTEMPTS=(int, 5),
    MIRES_ETL_SOURCE_CLEANUP_BACKOFF_BASE_SECONDS=(int, 60),
    MIRES_ETL_SOURCE_CLEANUP_BACKOFF_MAX_SECONDS=(int, 3600),
    MIRES_LOGGING_LEVEL=(str, "INFO"),
    MIRES_LOGGING_DIR=(Path, BASE_DIR / "LocalOnly/Logs"),
    MIRES_OIDC_CLIENT_ID=(str, None),
    MIRES_OIDC_CLIENT_SECRET=(str, None),
    MIRES_OIDC_DISCOVERY_URL=(str, None),
    MIRES_OIDC_LOG_CLAIMS=(bool, False),
    MIRES_OIDC_PROVIDER_DISPLAY_NAME=(str, "SSO"),
    MIRES_OIDC_ROLES_CLAIM=(str, "role"),
    MIRES_OIDC_FETCH_USERINFO=(bool, False),
    MIRES_OIDC_PKCE_ENABLED=(bool, False),
    MIRES_OIDC_UID_FIELD=(str, None),
    MIRES_SESSION_COOKIE_AGE=(int, 8 * 60 * 60),
    MIRES_SESSION_IDLE_TIMEOUT=(int, 30 * 60),
    MIRES_OLLAMA_URL=(str, "http://localhost:11434"),
    MIRES_OLLAMA_MODEL=(str, "qwen3-vl:8b-instruct-q8_0"),
    MIRES_OCR_MODE=(str, "hybrid"),
    MIRES_OCR_VLM_PAGE_TIMEOUT_SECONDS=(int, 900),
    MIRES_OCR_VLM_FORM_TIMEOUT_SECONDS=(int, 2700),
    MIRES_OCR_VLM_NUM_GPU=(int, 0),
    MIRES_OTLP_ENABLED=(bool, False),
    MIRES_OTLP_ENDPOINT=(str, "http://localhost:4318/v1/logs"),
    MIRES_OTLP_PROTOCOL=(str, "http"),
    MIRES_OTLP_INSECURE=(bool, False),
    MIRES_OTLP_SERVICE_NAME=(str, "miqa-research"),
    MIRES_TASK_CONSENT_ADFS_TOKEN_URL=(str, None),
    MIRES_TASK_CONSENT_RESOURCE=(str, None),
    MIRES_TASK_CONSENT_SKIP_CLIENT=(bool, False),
    MIRES_TASK_CONSENT_CLIENT_ID=(str, None),
    MIRES_TASK_CONSENT_CLIENT_SECRET=(str, None),
    MIRES_TASK_CONSENT_VAULT_PATH=(str, "mires/consent"),
    MIRES_TASK_CONSENT_BASE_URL=(str, None),
    MIRES_TASK_CONSENT_RESEARCH_PROJECT_NAME=(str, None),
    MIRES_TASK_CONSENT_UPLOAD_BUCKET=(str, None),
    MIRES_TASK_CONSENT_UPLOAD_PREFIX=(str, ""),
    MIRES_USE_VAULT=(bool, False),
    MIRES_VAULT_URL=(str, None),
    MIRES_VAULT_TOKEN=(str, None),
)

environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("MIRES_SECRET_KEY")

DEBUG = env("MIRES_DEBUG")

SESSION_COOKIE_SECURE = False if DEBUG else True
SESSION_EXPIRE_AT_BROWSER_CLOSE = False if DEBUG else True
SESSION_COOKIE_AGE = env("MIRES_SESSION_COOKIE_AGE")
SESSION_IDLE_TIMEOUT = env("MIRES_SESSION_IDLE_TIMEOUT")
AUDIT_LOG_RETENTION_DAYS = env("MIRES_AUDIT_LOG_RETENTION_DAYS")
# ADR 0024: data-access events (contract.constants.audit_log.DATA_ACCESS_EVENT_TYPES) are kept 10 years by default.
DATA_ACCESS_AUDIT_RETENTION_DAYS = env("MIRES_DATA_ACCESS_AUDIT_RETENTION_DAYS")

# DICOM storage (#122): the S3 connection settings, the destination bucket and the local/s3 toggle below.
# Ingestion itself is an ETL Job over an S3 Source Location (spec #411).
DICOM_S3_ENDPOINT_URL: str | None = env("MIRES_DICOM_S3_ENDPOINT_URL")
# Defaults to "us-east-1": most S3-compatible stores (RustFS included) still
# require *some* region for SigV4 signing even when they don't enforce AWS's
# region semantics.
DICOM_S3_REGION_NAME: str = env("MIRES_DICOM_S3_REGION_NAME")
DICOM_S3_ACCESS_KEY_ID: str | None = env("MIRES_DICOM_S3_ACCESS_KEY_ID")
DICOM_S3_SECRET_ACCESS_KEY: str | None = env("MIRES_DICOM_S3_SECRET_ACCESS_KEY")

# DICOM ingestion (#122): "local" (default) writes DicomFile.file to local
# disk exactly as before; "s3" writes it to DICOM_S3_BUCKET via the S3
# connection settings above instead. Read by data.models.dicom_storage's
# DicomStorage on every operation (not cached at process start), so the
# setting can flip without a schema migration. Only DicomFile.file is
# affected -- no other file storage in the app.
DICOM_STORAGE_BACKEND: str = env("MIRES_DICOM_STORAGE_BACKEND")
DICOM_S3_BUCKET: str | None = env("MIRES_DICOM_S3_BUCKET")

# ETL scripts (#144): same local/s3 toggle as DICOM_STORAGE_BACKEND above, but
# a separate setting and bucket -- an EtlScriptVersion's source is a small,
# operator-curated program, not patient data, and belongs in its own
# location. Read by data.models.etl_script's EtlScriptStorage on every
# operation. Only EtlScriptVersion.source is affected.
ETL_SCRIPT_STORAGE_BACKEND: str = env("MIRES_ETL_SCRIPT_STORAGE_BACKEND")
ETL_SCRIPT_S3_BUCKET: str | None = env("MIRES_ETL_SCRIPT_S3_BUCKET")
ETL_SCRIPT_S3_ENDPOINT_URL: str | None = env("MIRES_ETL_SCRIPT_S3_ENDPOINT_URL")
ETL_SCRIPT_S3_REGION_NAME: str = env("MIRES_ETL_SCRIPT_S3_REGION_NAME")
ETL_SCRIPT_S3_ACCESS_KEY_ID: str | None = env("MIRES_ETL_SCRIPT_S3_ACCESS_KEY_ID")
ETL_SCRIPT_S3_SECRET_ACCESS_KEY: str | None = env("MIRES_ETL_SCRIPT_S3_SECRET_ACCESS_KEY")

# ETL scripts (#144): global default for the max EtlScriptVersion.source size,
# in bytes. EtlProjectSettings.max_script_source_bytes overrides this per
# project (null defers here); a native script (project=None) always uses
# this default, since there's no project to hold an override.
ETL_SCRIPT_MAX_SOURCE_BYTES: int = env("MIRES_ETL_SCRIPT_MAX_SOURCE_BYTES")
# MIRES_ETL_SCRIPT_IMAGE_KEYS maps an uploaded Script source's (lowercased) file extension to the
# sandbox image key its Version runs on (#166) -- each key must also be in
# MIRES_SANDBOX_IMAGE_ALLOWLIST, below, for a Job to actually run.
ETL_SCRIPT_IMAGE_KEYS: dict[str, str] = json.loads(env("MIRES_ETL_SCRIPT_IMAGE_KEYS"))
# Native ETL Scripts (#226) are synced from the codebase after every migrate (ADR 0013's
# post_migrate precedent); `manage.py sync_native_etl_scripts` does the same on demand.
ETL_SYNC_NATIVE_SCRIPTS_ON_MIGRATE: bool = env("MIRES_ETL_SYNC_NATIVE_SCRIPTS_ON_MIGRATE")
# Connected Storages (#394): a JSON list of {name, kind, endpoint_url, region, access_key_id_env,
# secret_access_key_env}, synced into the database after every migrate (and by
# `manage.py sync_etl_storages`). Env-var *names* and Vault paths/key names are declared here, never a
# secret value (#396: access_key_id_vault_path/_vault_key, secret_access_key_vault_path/_vault_key).
# The built-in "Default" storage is the MIRES_ETL_S3_* settings above and needs no entry.
ETL_STORAGES: list[dict] = json.loads(env("MIRES_ETL_STORAGES"))

# ETL sandbox runner (#161, #165): MIRES_SANDBOX_BACKEND selects the SandboxBackend implementation
# ("compose" or "kubernetes"). MIRES_SANDBOX_DOCKER_HOST is where the Compose backend's
# Docker API connection points -- in production a per-worker-host docker-socket-proxy's TCP
# endpoint, never a raw mounted socket; local dev/test may point it straight at the daemon.
# MIRES_SANDBOX_IMAGE_ALLOWLIST is a JSON object mapping an image key (language + runtime +
# release, #147) to the image reference a Script's Binding is actually allowed to run --
# production should pin a full digest reference there, never a mutable tag. The remaining
# defaults are the platform's per-run resource ceiling (see MiqaResearch/etl_sandbox/limits.py for
# how a PipelineBinding may lower, never raise, timeout/memory/CPU below them).
SANDBOX_BACKEND: str = env("MIRES_SANDBOX_BACKEND")
SANDBOX_DOCKER_HOST: str = env("MIRES_SANDBOX_DOCKER_HOST")
# Compose only: pass `storage_opt size=` (inputs + outputs cap) to the sandbox container. Needs overlay2 on
# XFS with project quotas; on other storage drivers container creation fails, so it is off by default (#414).
SANDBOX_COMPOSE_STORAGE_LIMIT: bool = env("MIRES_SANDBOX_COMPOSE_STORAGE_LIMIT")
# ETL runner scratch volume (#414): each Job's inputs are fetched here (mode 0700, removed once the Job is
# finalized). It holds the original files, so deployments should use an encrypted volume. Empty = system temp
# dir. A Job needs free space >= its total listed input size + ETL_SCRATCH_MARGIN_BYTES, else it is retried as an
# infra-class failure.
ETL_SCRATCH_DIR: str = env("MIRES_ETL_SCRATCH_DIR")
ETL_SCRATCH_MARGIN_BYTES: int = env("MIRES_ETL_SCRATCH_MARGIN_BYTES")
SANDBOX_IMAGE_ALLOWLIST: dict[str, str] = json.loads(env("MIRES_SANDBOX_IMAGE_ALLOWLIST"))
SANDBOX_DEFAULT_TIMEOUT_SECONDS: int = env("MIRES_SANDBOX_DEFAULT_TIMEOUT_SECONDS")
SANDBOX_DEFAULT_MEMORY_MB: int = env("MIRES_SANDBOX_DEFAULT_MEMORY_MB")
SANDBOX_DEFAULT_CPU_MILLICORES: int = env("MIRES_SANDBOX_DEFAULT_CPU_MILLICORES")
SANDBOX_DEFAULT_PIDS_LIMIT: int = env("MIRES_SANDBOX_DEFAULT_PIDS_LIMIT")
SANDBOX_MAX_INPUT_BYTES: int = env("MIRES_SANDBOX_MAX_INPUT_BYTES")
SANDBOX_MAX_OUTPUT_BYTES: int = env("MIRES_SANDBOX_MAX_OUTPUT_BYTES")

# ETL sandbox runner, Kubernetes backend (#165): SANDBOX_K8S_NAMESPACE is the dedicated namespace the
# backend creates its per-run PVC/Pods/Job in (and idempotently ensures exists, along with a
# namespace-wide default-deny-egress NetworkPolicy). SANDBOX_K8S_STAGER_IMAGE is the small trusted
# utility image used by the short-lived transfer pods that move bytes on/off a run's PVC via pod-exec
# streaming (never the Script's own image, so it doesn't go through SANDBOX_IMAGE_ALLOWLIST) --
# production should still pin this to a digest, just not through the Script allowlist. The self-test
# settings configure the backend's own fail-closed health probe (see kubernetes_backend.py): a
# throwaway pod under the same NetworkPolicy must fail to reach EGRESS_PROBE_HOST:EGRESS_PROBE_PORT,
# cached for SELF_TEST_TTL_SECONDS -- confirmed necessary this session (#165's research spike) because
# a misconfigured CNI (e.g. kind's default kindnet) silently does not enforce NetworkPolicy at all.
SANDBOX_K8S_NAMESPACE: str = env("MIRES_SANDBOX_K8S_NAMESPACE")
SANDBOX_K8S_STAGER_IMAGE: str = env("MIRES_SANDBOX_K8S_STAGER_IMAGE")
SANDBOX_K8S_SELF_TEST_TTL_SECONDS: int = env("MIRES_SANDBOX_K8S_SELF_TEST_TTL_SECONDS")
SANDBOX_K8S_EGRESS_PROBE_HOST: str = env("MIRES_SANDBOX_K8S_EGRESS_PROBE_HOST")
SANDBOX_K8S_EGRESS_PROBE_PORT: int = env("MIRES_SANDBOX_K8S_EGRESS_PROBE_PORT")

# ETL orchestrator (#162): one platform-wide S3-compatible credential used to list/read every
# project's source buckets (per-project isolation is enforced in application code via
# EtlLocationGrant, not per-bucket IAM). ETL_POLL_INTERVAL_SECONDS is the Celery-beat fan-out
# cadence (one poll per PipelineBinding). ETL_LOG_RETENTION_DAYS is the global default for the
# daily log-prune task; EtlProjectSettings.log_retention_days overrides it per project.
# ETL_JOB_MAX_AUTO_RETRIES caps automatic retry of infra-class failures only (e.g. the configured
# SandboxBackend being unreachable) -- a script-class failure (bad exit code) or a config-class
# runner error (unknown image key, oversized input) never auto-retries. ETL_JOB_STUCK_GRACE_SECONDS
# is the extra grace period, on top of the Job's own resolved sandbox timeout, before a Job stuck
# in "running" (its worker vanished mid-run, with no heartbeat mechanism) is recovered.
USE_VAULT: bool = env("MIRES_USE_VAULT")
VAULT_URL: str | None = env("MIRES_VAULT_URL")
VAULT_TOKEN: str | None = env("MIRES_VAULT_TOKEN")
ETL_S3_ENDPOINT_URL: str | None = env("MIRES_ETL_S3_ENDPOINT_URL")
ETL_S3_REGION_NAME: str | None = env("MIRES_ETL_S3_REGION_NAME")


def _get_etl_s3_credentials() -> tuple[str | None, str | None]:
    """The Default Connected Storage's access key id and secret (#394). The MIRES_ETL_S3_* env vars win;
    otherwise, with Vault on, `AccessKeyId`/`SecretAccessKey` at MIRES_ETL_S3_VAULT_PATH. An unreachable or
    unseeded Vault leaves them unset (the browse/poll then reports missing credentials) instead of failing startup."""
    access_key_id = env("MIRES_ETL_S3_ACCESS_KEY_ID")
    secret_access_key = env("MIRES_ETL_S3_SECRET_ACCESS_KEY")
    if (access_key_id and secret_access_key) or not env("MIRES_USE_VAULT"):
        return access_key_id, secret_access_key
    try:
        vault_client = vault.get_vault_client(url=env("MIRES_VAULT_URL"), token=env("MIRES_VAULT_TOKEN"))
        path = env("MIRES_ETL_S3_VAULT_PATH")
        return (
            access_key_id or vault.get_vault_secret(vault_client, path, "AccessKeyId"),
            secret_access_key or vault.get_vault_secret(vault_client, path, "SecretAccessKey"),
        )
    except Exception:
        return access_key_id, secret_access_key


ETL_S3_ACCESS_KEY_ID, ETL_S3_SECRET_ACCESS_KEY = _get_etl_s3_credentials()
ETL_POLL_INTERVAL_SECONDS: int = env("MIRES_ETL_POLL_INTERVAL_SECONDS")
ETL_LOG_RETENTION_DAYS: int = env("MIRES_ETL_LOG_RETENTION_DAYS")
ETL_JOB_MAX_AUTO_RETRIES: int = env("MIRES_ETL_JOB_MAX_AUTO_RETRIES")
ETL_JOB_STUCK_GRACE_SECONDS: int = env("MIRES_ETL_JOB_STUCK_GRACE_SECONDS")

# ETL raw-bucket move (#163): a successful Job's inputs are copied to the raw bucket, verified,
# then the source is deleted. ETL_SOURCE_CLEANUP_MAX_ATTEMPTS caps the capped-backoff retry of
# that source delete (backoff = base * 2**(attempts-1), capped at the max); on cap exhaustion the
# input is escalated (one-time staff/Admin/Data-Manager email + audit event) and left in place.
ETL_SOURCE_CLEANUP_MAX_ATTEMPTS: int = env("MIRES_ETL_SOURCE_CLEANUP_MAX_ATTEMPTS")
ETL_SOURCE_CLEANUP_BACKOFF_BASE_SECONDS: int = env("MIRES_ETL_SOURCE_CLEANUP_BACKOFF_BASE_SECONDS")
ETL_SOURCE_CLEANUP_BACKOFF_MAX_SECONDS: int = env("MIRES_ETL_SOURCE_CLEANUP_BACKOFF_MAX_SECONDS")

# DICOM ingestion security (#114, #127): a file's *declared* Rows/Columns/
# TotalPixelMatrixRows/TotalPixelMatrixColumns/NumberOfFrames tags are
# rejected before any pixel data is decoded when they exceed these bounds --
# defense against a small compressed payload declaring an enormous decoded
# size (a decompression-bomb shape, especially relevant to pathology J2K
# frames). Defaults are generous enough for real gigapixel WSI pyramids
# (tunable per deployment via env).
DICOM_MAX_PIXEL_DIMENSIONS: int = env("MIRES_DICOM_MAX_PIXEL_DIMENSIONS")
DICOM_MAX_FRAME_COUNT: int = env("MIRES_DICOM_MAX_FRAME_COUNT")

# Orphan DICOM blob sweep (#420): a blob under DICOM/ with no DicomFile row is reported after
# DETECT hours (outlasts the longest ETL Job) and deleted after GRACE hours, only if it was already
# reportable at the previous run. Nothing is deleted if the deletable set exceeds MAX_DELETE_COUNT or
# MAX_DELETE_FRACTION of listed blobs. SWEEP_ACTION (report | delete) governs the daily task.
DICOM_ORPHAN_DETECT_HOURS: int = env("MIRES_DICOM_ORPHAN_DETECT_HOURS")
DICOM_ORPHAN_GRACE_HOURS: int = env("MIRES_DICOM_ORPHAN_GRACE_HOURS")
DICOM_ORPHAN_MAX_DELETE_COUNT: int = env("MIRES_DICOM_ORPHAN_MAX_DELETE_COUNT")
DICOM_ORPHAN_MAX_DELETE_FRACTION: float = env("MIRES_DICOM_ORPHAN_MAX_DELETE_FRACTION")
DICOM_ORPHAN_SWEEP_ACTION: str = env("MIRES_DICOM_ORPHAN_SWEEP_ACTION")


def get_allowed_hosts_list(allowed_hosts_env) -> list[str]:
    if allowed_hosts_env is not None:
        return [host.strip() for host in allowed_hosts_env.split(",")]

    return []

ALLOWED_HOSTS = get_allowed_hosts_list(env("MIRES_ALLOWED_HOSTS"))
CSRF_TRUSTED_ORIGINS = get_allowed_hosts_list(env("MIRES_CSRF_TRUSTED_ORIGINS"))

ADMIN_URL: str = f"{env('MIRES_ADMIN_URL').removeprefix("/") if env('MIRES_ADMIN_URL') else 'miresadm'}"

# Application definition

INSTALLED_APPS = [
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'django.contrib.postgres',
    'allauth',
    'allauth.account',
    'allauth.mfa',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.openid_connect',
    'oauth2_provider',
    'ninja',
    'django_htmx',
    'django.contrib.sites',
    'documentation',
    # Unfold admin interface
    'unfold',
    'unfold.contrib.filters',
    'unfold.contrib.forms',
    # 'unfold.contrib.inlines',
    # 'unfold.contrib.import_export',
    # 'unfold.contrib.guardian',
    # 'unfold.contrib.simple_history',
    # 'unfold.contrib.location_field',
    'django.contrib.admin',
    'django_celery_beat',
    'django_celery_results',
    'MiqaResearch.data',
    'kpforms',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'MiqaResearch.middleware.SessionTimeoutMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'MiqaResearch.middleware.AsyncUserMiddleware',
    'allauth.account.middleware.AccountMiddleware',
    'django_htmx.middleware.HtmxMiddleware',
]

if DEBUG:
    INSTALLED_APPS += ['debug_toolbar']
    MIDDLEWARE = MIDDLEWARE[:1] + ["debug_toolbar.middleware.DebugToolbarMiddleware"] + MIDDLEWARE[1:]


INTERNAL_IPS = [
    '127.0.0.1',
    'localhost',
]

def show_debug_toolbar(request):
    """Skip the default INTERNAL_IPS check (Docker gateway IP never matches).

    Read django.conf.settings at call time: the test runners (Django, pytest-django)
    force settings.DEBUG=False, unlike this module's DEBUG global, so tests are excluded.
    """
    from django.conf import settings as django_settings
    return django_settings.DEBUG


DEBUG_TOOLBAR_CONFIG = {
    'SHOW_TOOLBAR_CALLBACK': 'MiqaResearch.settings.show_debug_toolbar',
}

ROOT_URLCONF = 'MiqaResearch.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.debug',
                'MiqaResearch.context_processors.auth_framework',
            ],
            'builtins': [
                'django.templatetags.i18n',
            ],
        },
    },
]

WSGI_APPLICATION = 'MiqaResearch.wsgi.application'

# =======================
# AUTHENTICATION SETTINGS
# =======================
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

MIRES_AUTHENTICATION_FRAMEWORK = env("MIRES_AUTHENTICATION_FRAMEWORK")
_AUTH_MODES = set(MIRES_AUTHENTICATION_FRAMEWORK.split(","))

OIDC_PROVIDER_ID = "mires-oidc"
OIDC_LOGIN_ENABLED = bool({"oidc", "adfs"} & _AUTH_MODES)
SSO_ONLY_LOGIN_ENABLED = OIDC_LOGIN_ENABLED and _AUTH_MODES <= {"oidc", "adfs"}
OIDC_PROVIDER_DISPLAY_NAME = env("MIRES_OIDC_PROVIDER_DISPLAY_NAME")
OIDC_ROLES_CLAIM = env("MIRES_OIDC_ROLES_CLAIM")
OIDC_LOG_CLAIMS = env("MIRES_OIDC_LOG_CLAIMS", default=DEBUG)

if OIDC_LOGIN_ENABLED:
    if "adfs" in _AUTH_MODES:
        _oidc_server_url = f"{env('MIRES_ADFS_AUTHORITY').rstrip('/')}/adfs/.well-known/openid-configuration"
    else:
        _oidc_server_url = env("MIRES_OIDC_DISCOVERY_URL")

    SOCIALACCOUNT_PROVIDERS = {
        "openid_connect": {
            "APPS": [
                {
                    "provider_id": OIDC_PROVIDER_ID,
                    "name": OIDC_PROVIDER_DISPLAY_NAME,
                    "client_id": env("MIRES_OIDC_CLIENT_ID"),
                    "secret": env("MIRES_OIDC_CLIENT_SECRET"),
                    "settings": {"server_url": _oidc_server_url},
                }
            ]
        }
    }
    if env("MIRES_OIDC_FETCH_USERINFO"):
        SOCIALACCOUNT_PROVIDERS["openid_connect"]["APPS"][0]["settings"]["fetch_userinfo"] = True
    if env("MIRES_OIDC_PKCE_ENABLED"):
        SOCIALACCOUNT_PROVIDERS["openid_connect"]["APPS"][0]["settings"]["oauth_pkce_enabled"] = True
    if env("MIRES_OIDC_UID_FIELD"):
        SOCIALACCOUNT_PROVIDERS["openid_connect"]["APPS"][0]["settings"]["uid_field"] = env("MIRES_OIDC_UID_FIELD")
    # ADFS/OIDC often omits a reliable `email_verified` claim; trust the IdP's
    # email outright rather than depending on that claim being present.
    SOCIALACCOUNT_PROVIDERS["openid_connect"]["APPS"][0]["settings"]["verified_email"] = True
    SOCIALACCOUNT_PROVIDERS["openid_connect"]["APPS"][0]["settings"]["email_authentication"] = True
    SOCIALACCOUNT_ADAPTER = "helpers.authentication.custom_oidc_backend.CustomSocialAccountAdapter"

SITE_ID = 1

LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'

ACCOUNT_LOGIN_METHODS = {'email'}
ACCOUNT_SIGNUP_FIELDS = ['email*', 'password1*', 'password2*']
ACCOUNT_EMAIL_VERIFICATION = 'optional'

# Auto-link a first-time SSO login to an existing local account when the
# claimed email matches, with no password-confirmation step. allauth's
# wipe_password() safety net (fires only on the unverified-match fallback
# path) is intentionally left in place as the defense against email-collision
# account takeover.
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True

MFA_SUPPORTED_TYPES = ["webauthn"]
MFA_PASSKEY_LOGIN_ENABLED = True

# Webauthn strictly requires HTTPS. During development when running on HTTP we need this to make, e.g.,
# the fido2 library to not reject the origin
MFA_WEBAUTHN_ALLOW_INSECURE_ORIGIN = DEBUG

# ADFS OIDC authentication

# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases
DEFAULT_SQLITE_DATABASE_PATH = BASE_DIR / "db.sqlite3"
DATABASES = {
    "default": (
        env.db(
            "MIRES_DATABASE_URL",
            default=f"sqlite:////{DEFAULT_SQLITE_DATABASE_PATH.as_posix()}",
        )
        if env("MIRES_DB_HOST") is None
        else (
            {
                "ENGINE": env("MIRES_DB_ENGINE"),
                "NAME": env("MIRES_DB_DATABASE"),
                "User": env("MIRES_DB_USER"),
                "Password": env("MIRES_DB_PASSWORD"),
                "Host": env("MIRES_DB_HOST"),
                "Port": env("MIRES_DB_PORT"),
            }
            | {"OPTIONS": {"sslmode": env("MIRES_DB_SSLMODE")}}
            if env("MIRES_DB_SSLMODE")
            else {}
        )
    )
}

CACHES = {
    "default": {
        "BACKEND": env("MIRES_CACHE_BACKEND"),
        "LOCATION": env("MIRES_CACHE_LOCATION"),
    }
}

if env("MIRES_LOGGING_DIR") is not None and not env("MIRES_LOGGING_DIR").exists():
    env("MIRES_LOGGING_DIR").mkdir(parents=True, exist_ok=True)

# OTLP log export (#293): off unless MIRES_OTLP_ENABLED; OTLP/HTTP only.
_OTLP_HANDLERS = otlp_logging_config(
    enabled=env("MIRES_OTLP_ENABLED"),
    endpoint=env("MIRES_OTLP_ENDPOINT"),
    service_name=env("MIRES_OTLP_SERVICE_NAME"),
)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "jsonlog": {
            "format": (
                '{"timestamp":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s",'
                '"file":"%(filename)s","line":%(lineno)d,"message":"%(message)s"}'
            ),
        },
        "conventional": {
            "format": "%(asctime)s | %(levelname)s | [%(name)s] [%(filename)s:%(lineno)d] | %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "conventional",
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": env("MIRES_LOGGING_DIR") / "miqa_research.log",
            "maxBytes": 1024 * 1024 * 5,  # 5 MB
            "backupCount": 5,
            "formatter": "conventional",
        },
        **_OTLP_HANDLERS,
    },
    "root": {
        "handlers": ["console", "file", *_OTLP_HANDLERS],
        "level": env("MIRES_LOGGING_LEVEL"),
    },
}



# E-Identitet Settings
EID_CLIENT_ID = env("MIRES_EID_CLIENT_ID", default=None)
EID_CLIENT_SECRET = env("MIRES_EID_CLIENT_SECRET", default=None)

# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/6.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

LANGUAGES = [("en", "English")]

USE_TZ = True

# Email
EMAIL_BACKEND = env("MIRES_EMAIL_BACKEND")
EMAIL_HOST = env("MIRES_EMAIL_HOST")
EMAIL_PORT = env("MIRES_EMAIL_PORT")
EMAIL_HOST_USER = env("MIRES_EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = env("MIRES_EMAIL_HOST_PASSWORD")
EMAIL_USE_SSL = env("MIRES_EMAIL_USE_TLS")

NO_REPLY_EMAIL_ADDRESS = env("MIRES_EMAIL_NOREPLY_SENDER")

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.0/howto/static-files/

STATIC_ROOT = env("MIRES_STATIC_ROOT")
STATIC_URL = env("MIRES_STATIC_URL")
STATICFILES_DIRS = [BASE_DIR / "static"]
STATICFILES_FINDERS = [
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
]

MEDIA_ROOT = env("MIRES_MEDIA_ROOT")

# In-app manuals: JSON builds from documentation/build_manuals.py, laid out as <manual>/<locale>/.
MANUALS_BUILD_DIR = BASE_DIR / "documentation" / "builds"

# ==============================
# SENSITIVE DATA ENCRYPTION
# ==============================
FERNET_KEY, SENSITIVE_DATA_HASH_KEY = (
    get_data_encryption_keys(env, env("MIRES_DATA_HASH_FERNET_KEY_ENCRYPTION"))
    if env("MIRES_USE_VAULT")
    else (None, None)
)

# ==============================
# DJANGO TASKS & CELERY
# ==============================
TASKS = {
    "default": {
        "BACKEND": "django_tasks_celery.CeleryBackend", # See: https://github.com/oliverhaas/django-tasks-celery
        "QUEUES": [
            "default", QUEUE_OCR, QUEUE_EMAIL, QUEUE_GET_CONSENTS, QUEUE_CALCULATE_CONSENT_STATISTICS,
            QUEUE_DICOM_INGESTION, QUEUE_ETL_POLL, QUEUE_ETL_RUN,
        ],
    }
}
CELERY_BROKER_URL = env("MIRES_CELERY_BROKER_URL", default="amqp://guest:guest@miresrabbit:5672//")
CELERY_BROKER_RETRY_ON_STARTUP = True
CELERY_BROKER_TRANSPORT_OPTIONS = {"confirm": True, "fanout_prefix": True}
# RabbitMQ 4.x removed support for transient non-exclusive queues, which kombu's pidbox
# (Mingle) and event (Gossip) queues use by default. Marking them exclusive keeps them
# transient but makes RabbitMQ accept them again. See https://github.com/celery/kombu/issues/2338
CELERY_CONTROL_QUEUE_EXCLUSIVE = True
CELERY_EVENT_QUEUE_EXCLUSIVE = True
CELERY_RESULT_BACKEND = env("MIRES_CELERY_RESULT_BACKEND")
CELERY_RESULT_EXTENDED = env("MIRES_CELERY_RESULT_EXTENDED")
CELERY_TASK_DEFAULT_QUEUE_TYPE = "quorum"
CELERY_TASK_TRACK_STARTED = env("MIRES_CELERY_TASK_TRACK_STARTED")
CELERY_TASK_TIME_LIMIT = env("MIRES_CELERY_TASK_TIME_LIMIT")
CELERY_TIMEZONE = env("MIRES_CELERY_TIMEZONE")
CELERY_WORKER_ENABLE_REMOTE_CONTROL = env("MIRES_CELERY_WORKER_ENABLE_REMOTE_CONTROL", default=False)
CELERY_WORKER_PREFETCH_MULTIPLIER = env("MIRES_CELERY_WORKER_PREFETCH_MULTIPLIER", default=1)
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"


# =======================================================
# EXTRA SETTINGS FOR TASKS AND THIRD PARTY INTEGRATIONS
# =======================================================
# OAUTH2
# Spelled out so data.ClientBinding can point at the (swappable) Application model in migrations.
OAUTH2_PROVIDER_APPLICATION_MODEL = "oauth2_provider.Application"
OAUTH2_PROVIDER = {
    "SCOPES": {
        SCOPE_READ: "Read access to all data endpoints except ones with higher permission requirements",
        SCOPE_UPSERT_CONSENT: "Upsert study participant consents",
        SCOPE_MONITOR_CLIENT: "Access the MIQA Monitor client API",
        SCOPE_ADMIN: "Full administrative access to MIQA Research",
        SCOPE_DICOM_RAW: "Raw DICOM files (original UIDs, full PHI) from the WADO endpoints, within the Client Binding",
    },
    # Which scopes a client may obtain depends on its Client Binding (ADR 0027).
    "SCOPES_BACKEND_CLASS": "MiqaResearch.interfaces.http.api.client_scopes.ClientBindingScopes",
    "DEFAULT_SCOPES": ["read"],
}

# Ollama Settings
OLLAMA_URL = env("MIRES_OLLAMA_URL")
OLLAMA_MODEL = env("MIRES_OLLAMA_MODEL")

# PROM OCR pipeline mode: "hybrid" (Classic Path + VLM escalation, default) or
# "vlm_only" (docs/prom-ocr-handoff.md §10.2, wayfinder map #60, #62)
OCR_MODE = env("MIRES_OCR_MODE")

# PROM OCR VLM fallback budgets (docs/prom-ocr-handoff.md §2 -- optimistic pending
# real-hardware validation, see #17's M5 Max caveat)
OCR_VLM_PAGE_TIMEOUT_SECONDS = env("MIRES_OCR_VLM_PAGE_TIMEOUT_SECONDS")
OCR_VLM_FORM_TIMEOUT_SECONDS = env("MIRES_OCR_VLM_FORM_TIMEOUT_SECONDS")
OCR_VLM_NUM_GPU = env("MIRES_OCR_VLM_NUM_GPU")


# Participant consent settings
def _get_consent_client_id_and_secret():
    if env("MIRES_TASK_CONSENT_SKIP_CLIENT"):
        return None, None

    client_id = env("MIRES_TASK_CONSENT_CLIENT_ID")
    client_secret = env("MIRES_TASK_CONSENT_CLIENT_SECRET")
    if client_id is None or client_secret is None:
        if env("MIRES_USE_VAULT") is False:
            return None, None

        vault_client = vault.get_vault_client(
            url=env("MIRES_VAULT_URL"),
            token=env("MIRES_VAULT_TOKEN"),
        )
        return (
            vault.get_vault_secret(vault_client, env("MIRES_TASK_CONSENT_VAULT_PATH"), "ConsentClientId"),
            vault.get_vault_secret(vault_client, env("MIRES_TASK_CONSENT_VAULT_PATH"), "ConsentClientSecret"),
        )
    return client_id, client_secret

TASK_CONSENT_ADFS_TOKEN_URL = env("MIRES_TASK_CONSENT_ADFS_TOKEN_URL")
TASK_CONSENT_RESOURCE = env("MIRES_TASK_CONSENT_RESOURCE")
TASK_CONSENT_CLIENT_ID, TASK_CONSENT_CLIENT_SECRET = _get_consent_client_id_and_secret()
TASK_CONSENT_BASE_URL = env("MIRES_TASK_CONSENT_BASE_URL")
TASK_CONSENT_RESEARCH_PROJECT_NAME: str = env("MIRES_TASK_CONSENT_RESEARCH_PROJECT_NAME")
# Where fetch_participant_consent writes each export (key layout: its `_export_key`), via the
# MIRES_ETL_S3_* credential. A Pipeline Binding on that location loads it (#241).
TASK_CONSENT_UPLOAD_BUCKET: str | None = env("MIRES_TASK_CONSENT_UPLOAD_BUCKET")
TASK_CONSENT_UPLOAD_PREFIX: str = env("MIRES_TASK_CONSENT_UPLOAD_PREFIX")

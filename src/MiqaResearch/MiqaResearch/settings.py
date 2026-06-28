from pathlib import Path
from typing import Any

import environ
from more_itertools.more import lstrip

from contract.constants.scopes import (
    SCOPE_ADMIN,
    SCOPE_MONITOR_CLIENT,
    SCOPE_READ,
    SCOPE_UPSERT_CONSENT,
)
from helpers import vault

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    MIRES_ADMIN_URL=(str, "miresadm"),
    MIRES_ADFS_SERVER=(str, "ADFS server URL"),
    MIRES_ADFS_TENANT=(str, "adfs"),
    MIRES_ADFS_CLIENT_ID=(str, "SomeClientId"),
    MIRES_ADFS_RESOURCE=(str, None),
    MIRES_ADFS_POST_LOGOUT_REDIRECT_URI=(str, "http://localhost:8000/loggedOut"),
    MIRES_ADFS_CALLBACK_PATH=(str, "/signin-oidc"),
    MIRES_ADFS_AUTHORITY=(),
    MIRES_AUTHENTICATION_EMAIL_CLAIM=(str, "email"),
    MIRES_AUTHENTICATION_FRAMEWORK=(str, "yubikey"),
    MIRES_AUTHENTICATION_FIRST_NAME_CLAIM=(str, "givenname"),
    MIRES_AUTHENTICATION_LAST_NAME_CLAIM=(str, "surname"),
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
    MIRES_EMAIL_HOST=(str, None),
    MIRES_EMAIL_PORT=(int, 1234),
    MIRES_EMAIL_HOST_USER=(str, None),
    MIRES_EMAIL_HOST_PASSWORD=(str, None),
    MIRES_EMAIL_USE_TLS=(bool, True),
    MIRES_EMAIL_BACKEND=(str, "django.core.mail.backends.smtp.EmailBackend"),
    MIRES_EMAIL_NOREPLY_SENDER=(str, "noreply@miqaresearch.se"),
    MIRES_EID_CLIENT_ID=(str, None),
    MIRES_EID_CLIENT_SECRET=(str, None),
    MIRES_LOGGING_LEVEL=(str, "INFO"),
    MIRES_LOGGING_DIR=(Path, BASE_DIR / "LocalOnly/Logs"),
    MIRES_OIDC_CLIENT_ID=(str, None),
    MIRES_OIDC_CLIENT_SECRET=(str, None),
    MIRES_OIDC_ROLES_CLAIM=(str, "role"),
    MIRES_OLLAMA_URL=(str, "http://localhost:11434"),
    MIRES_OLLAMA_MODEL=(str, "gemma4"),
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
    MIRES_VAULT_URL=(str, None),
    MIRES_VAULT_TOKEN=(str, None),
)

environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("MIRES_SECRET_KEY")

DEBUG = env("MIRES_DEBUG")

SESSION_COOKIE_SECURE = False if DEBUG else True
SESSION_EXPIRE_AT_BROWSER_CLOSE = False if DEBUG else True


def get_allowed_hosts_list(allowed_hosts_env) -> list[str]:
    if allowed_hosts_env is not None:
        return [host.strip() for host in allowed_hosts_env.split(",")]

    return []

ALLOWED_HOSTS = get_allowed_hosts_list(env("MIRES_ALLOWED_HOSTS"))
CSRF_TRUSTED_ORIGINS = get_allowed_hosts_list(env("MIRES_CSRF_TRUSTED_ORIGINS"))

ADMIN_URL: str = f"{env('MIRES_ADMIN_URL').removeprefix("/") if env('MIRES_ADMIN_URL') else 'miresadm'}"

# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
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
    'oauth2_provider',
    'ninja',
    'django_celery_beat',
    'django_celery_results',
    'django_htmx',
    'django.contrib.sites',
    'MiqaResearch.data',
    #'documentation',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'MiqaResearch.middleware.AsyncUserMiddleware',
    'allauth.account.middleware.AccountMiddleware',
    'django_htmx.middleware.HtmxMiddleware',
]

if DEBUG:
    INSTALLED_APPS += ['debug_toolbar']
    MIDDLEWARE += ["debug_toolbar.middleware.DebugToolbarMiddleware"]


INTERNAL_IPS = [
    '127.0.0.1',
    'localhost',
]

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

if env("MIRES_AUTHENTICATION_FRAMEWORK") == "adfs":
    def _get_secrets_from_vault(secret_paths_and_name: list[tuple[str, str]]) -> list[Any]:
        vault_client = vault.get_vault_client(
            url=env("MIRES_VAULT_URL"),
            token=env("MIRES_VAULT_TOKEN"),
        )
        return [
            vault.get_vault_secret(vault_client, secret_path, secret_name)
            for secret_path, secret_name in secret_paths_and_name
        ]

    INSTALLED_APPS.append("django_auth_adfs")
    MIDDLEWARE.append("django_auth_adfs.middleware.LoginRequiredMiddleware")

    AUTHENTICATION_BACKENDS.append("django_auth_adfs.backend.AdfsAuthCodeBackend")
    AUTH_ADFS = {
        "SERVER": env("MIRES_ADFS_AUTHORITY"),
        "DISABLE_SSO": True,
        "CLIENT_ID": _get_secrets_from_vault([("mires/adfs", "ClientId")])[0],
        "TENANT": env("MIRES_ADFS_TENANT"),
        "RELYING_PARTY_ID": env("MIRES_ADFS_RESOURCE"),
        "AUDIENCE": env("MIRES_ADFS_RESOURCE"),
        "LOGIN_EXEMPT_URLS": [
            r"^admin/",
            r"^static/",
            r"^favicon\.ico$",
        ],
        "RESOURCE": env("MIRES_ADFS_RESOURCE"),
        "POST_LOGOUT_REDIRECT_URI": env("MIRES_ADFS_POST_LOGOUT_REDIRECT_URI"),
        "CALLBACK_PATH": env("MIRES_ADFS_CALLBACK_PATH"),
        "LOGIN_CALLBACK_URL": env("MIRES_ADFS_CALLBACK_PATH"),
        "CLAIM_MAPPING": {
            "first_name": env("MIRES_AUTHENTICATION_FIRST_NAME_CLAIM"),
            "last_name": env("MIRES_AUTHENTICATION_LAST_NAME_CLAIM"),
            "email": env("MIRES_AUTHENTICATION_EMAIL_CLAIM"),
        },
    }

elif env("MIRES_AUTHENTICATION_FRAMEWORK") == "oidc":
    INSTALLED_APPS.append("mozilla_django_oidc")
    AUTHENTICATION_BACKENDS.append("mozilla_django_oidc.auth.OIDCAuthenticationBackend")
    OIDC_RP_CLIENT_ID = env("MIRES_OIDC_CLIENT_ID")
    OIDC_RP_CLIENT_SECRET = env("MIRES_OIDC_CLIENT_SECRET")
    OIDC_OP_JWKS_ENDPOINT = f"{env('MIRES_ADFS_AUTHORITY').rstrip('/')}/discovery/keys"
    OIDC_OP_AUTHORIZATION_ENDPOINT = f"{env('MIRES_ADFS_AUTHORITY').rstrip('/')}/oauth2/authorize"
    OIDC_OP_TOKEN_ENDPOINT = f"{env('MIRES_ADFS_AUTHORITY').rstrip('/')}/oauth2/token"
    OIDC_OP_USER_ENDPOINT = f"{env('MIRES_ADFS_AUTHORITY').rstrip('/')}/oauth2/userinfo"
    OIDC_RP_SIGN_ALGO = "RS256"
    OIDC_ROLES_CLAIM = env("MIRES_OIDC_ROLES_CLAIM")

SITE_ID = 1

LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'

ACCOUNT_LOGIN_METHODS = {'email'}
ACCOUNT_SIGNUP_FIELDS = ['email*', 'password1*', 'password2*']
ACCOUNT_EMAIL_VERIFICATION = 'optional'

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

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "jsonlog": {
            "format": '{"timestamp":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","file":"%(filename)s","line":%(lineno)d,"message":"%(message)s"}',
        },
        "conventional":{
            "format": "%(asctime)s | %(levelname)s | [%(name)s] [%(filename)s:%(lineno)d] | %(message)s",
        }
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
        }
    },
    "root": {
        "handlers": ["console", "file"],
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

STATIC_ROOT_IGNORES = ["less", "webcomponents"]

# ==============================
# SENSITIVE DATA ENCRYPTION
# ==============================
FERNET_KEY = b"EiGdHopiKZdBZwVCP4dVJitPrrDnOuGAd94W4EZpwQc="  # TODO: Change so that this key comes from Vault
SENSITIVE_DATA_HASH_KEY = "H2QCB14temR-C2JnLORSE5TxPwLd8iy3YygNPQ-corA="  # TODO: Change so that this key comes from VAULT

# ==============================
# CELERY
# ==============================
CELERY_BROKER_URL = env("MIRES_CELERY_BROKER_URL", default="amqp://guest:guest@oqarabbit:5672//")
CELERY_BROKER_RETRY_ON_STARTUP = True
CELERY_BROKER_TRANSPORT_OPTIONS = {"confirm": True, "fanout_prefix": True}
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
OAUTH2_PROVIDER = {
    "SCOPES": {
        SCOPE_READ: "Read access to all data endpoints except ones with higher permission requirements",
        SCOPE_UPSERT_CONSENT: "Upsert study participant consents",
        SCOPE_MONITOR_CLIENT: "Access the MIQA Monitor client API",
        SCOPE_ADMIN: "Full administrative access to MIQA Research",
    },
    "DEFAULT_SCOPES": ["read"],
}

# Ollama Settings
OLLAMA_URL = env("MIRES_OLLAMA_URL")
OLLAMA_MODEL = env("MIRES_OLLAMA_MODEL")


# Participant consent settings
def _get_consent_client_id_and_secret():
    if env("MIRES_TASK_CONSENT_SKIP_CLIENT"):
        return None, None

    client_id = env("MIRES_TASK_CONSENT_CLIENT_ID")
    client_secret = env("MIRES_TASK_CONSENT_CLIENT_SECRET")
    if client_id is None or client_secret is None:
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
TASK_CONSENT_FORM_COL_NAME = env("MIRES_TASK_CONSENT_FORM_COL_NAME", default="Namn")
TASK_CONSENT_FORM_COL_PID = env("MIRES_TASK_CONSENT_FORM_COL_PID", default="Personnummer")
TASK_CONSENT_FORM_COL_STATUS = env("MIRES_TASK_CONSENT_FORM_COL_STATUS", default="Status")
TASK_CONSENT_FORM_COL_SIGNED = env("MIRES_TASK_CONSENT_FORM_COL_SIGNED", default="Signerat")
TASK_CONSENT_FORM_COL_LAST_UPDATED = env("MIRES_TASK_CONSENT_FORM_COL_LAST_UPDATED", default="Senast Uppdaterad")
TASK_CONSENT_FORM_COL_RETRACTED = env("MIRES_TASK_CONSENT_FORM_COL_RETRACTED", default="Återtaget")
TASK_CONSENT_FORM_COL_CLINIC = env("MIRES_TASK_CONSENT_FORM_COL_CLINIC", default="klinik")
TASK_CONSENT_FORM_COL_RESEARCH_PERSON_INFORMATION = env("MIRES_TASK_CONSENT_FORM_COL_RESEARCH_PERSON_INFORMATION", default="fpi")
TASK_CONSENT_FORM_COL_READ_INFORMATION = env("MIRES_TASK_CONSENT_FORM_COL_READ_INFORMATION", default='Jag har läst och förstått "Information till forskningspersoner"')
TASK_CONSENT_FORM_COL_COMMENT = env("MIRES_TASK_CONSENT_FORM_COL_COMMENT", default="Kommentar")
TASK_CONSENT_FORM_CONSENTED_TRUE_VALUES = [
    val.strip() for val in env("MIRES_TASK_CONSENT_FORM_COL_CONSENTED_TRUE_VALUES", default="Ja,").split(",")]
TASK_CONSENT_TIMEZONE: str = env("MIRES_TASK_CONSENT_TIMEZONE", default="Europe/Stockholm")

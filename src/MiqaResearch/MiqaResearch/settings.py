from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
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
    MIRES_EMAIL_HOST=(str, None),
    MIRES_EMAIL_PORT=(int, 1234),
    MIRES_EMAIL_HOST_USER=(str, None),
    MIRES_EMAIL_HOST_PASSWORD=(str, None),
    MIRES_EMAIL_USE_TLS=(bool, True),
    MIRES_EMAIL_BACKEND=(str, "django.core.mail.backends.smtp.EmailBackend"),
    MIRES_NOREPLY_SENDER_EMAIL=(str, "noreply@miqaresearch.se"),
    MIRES_EID_CLIENT_ID=(str, None),
    MIRES_EID_CLIENT_SECRET=(str, None),
    MIRES_OLLAMA_URL=(str, "http://localhost:11434"),
    MIRES_OLLAMA_MODEL=(str, "gemma3"),
)

environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("MIRES_SECRET_KEY")

DEBUG = env("MIRES_DEBUG", default=False)

SESSION_COOKIE_SECURE = False if DEBUG else True
SESSION_EXPIRE_AT_BROWSER_CLOSE = False if DEBUG else True


def get_allowed_hosts_list(allowed_hosts_env) -> list[str]:
    if allowed_hosts_env is not None:
        return [host.strip() for host in allowed_hosts_env.split(",")]

    return []

ALLOWED_HOSTS = get_allowed_hosts_list(env("MIRES_ALLOWED_HOSTS"))
CSRF_TRUSTED_ORIGINS = get_allowed_hosts_list(env("MIRES_CSRF_TRUSTED_ORIGINS"))


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
    'django_htmx',
    'django.contrib.sites',
    'MiqaResearch.data',
    'documentation',
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


# E-Identitet Settings
EID_CLIENT_ID = env("MIRES_EID_CLIENT_ID", default=None)
EID_CLIENT_SECRET = env("MIRES_EID_CLIENT_SECRET", default=None)

# Ollama Settings
OLLAMA_URL = env("MIRES_OLLAMA_URL")
OLLAMA_MODEL = env("MIRES_OLLAMA_MODEL")

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

NO_REPLY_EMAIL_ADDRESS = env("MIRES_NOREPLY_SENDER_EMAIL")

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

"""Regression tests for #170: MIRES_MEDIA_ROOT declared in the env() schema
but never actually assigned to Django's MEDIA_ROOT setting (silently left at
Django's own empty-string default, resolved by FileSystemStorage relative to
the process CWD rather than any configured path).
"""
import os
import subprocess
import sys

from django.conf import settings

from MiqaResearch.settings import BASE_DIR


def test_media_root_defaults_to_mires_media_root_schema_default():
    """No MIRES_MEDIA_ROOT override in this process's env: MEDIA_ROOT must
    still be the env() schema's declared default (BASE_DIR / "media"), not
    Django's own empty-string default.
    """
    assert settings.MEDIA_ROOT == BASE_DIR / "media"


def test_media_root_follows_an_explicit_mires_media_root_env_var(tmp_path):
    """An explicit MIRES_MEDIA_ROOT must actually reach settings.MEDIA_ROOT.

    Runs in a fresh subprocess (same shape as the issue's own repro) rather
    than reloading MiqaResearch.settings in-process: the settings module
    does module-level work gated on other env vars (e.g. Vault-backed
    encryption keys) that a bare reload shouldn't risk triggering.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import django, os\n"
            "os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'MiqaResearch.settings')\n"
            "django.setup()\n"
            "from django.conf import settings\n"
            "print(settings.MEDIA_ROOT)\n",
        ],
        cwd=BASE_DIR,
        env={**os.environ, "MIRES_MEDIA_ROOT": str(tmp_path)},
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == str(tmp_path)

"""
Root pytest configuration.

The settings module connects to Vault at import time to fetch encryption
keys.  For local test runs (no Vault available) we inject deterministic
fallback keys so that the application can be exercised without an external
dependency.  When Vault *is* available (CI / Docker) the real keys are used.
"""
import os

# Provide fallback encryption keys when Vault is not reachable so that
# `manage.py` / `pytest` can start in a local dev/test environment.
os.environ.setdefault("MIRES_FERNET_KEY", "EiGdHopiKZdBZwVCP4dVJitPrrDnOuGAd94W4EZpwQc=")
os.environ.setdefault("MIRES_SENSITIVE_DATA_HASH_KEY", "H2QCB14temR-C2JnLORSE5TxPwLd8iy3YygNPQ-corA=")

import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _no_native_etl_script_sync_on_test_migrate():
    """Tests that need native ETL Scripts create or sync them explicitly -- the test database starts
    without them, so "no native scripts" states stay testable. Session-scoped autouse, so it runs
    before pytest-django migrates the test database (the post_migrate sync reads this setting)."""
    from django.conf import settings

    settings.ETL_SYNC_NATIVE_SCRIPTS_ON_MIGRATE = False


@pytest.fixture(autouse=True)
def _dummy_tasks_backend(settings):
    """Signals enqueue tasks; never hit a real broker in tests."""
    settings.TASKS = {
        "default": {
            "BACKEND": "django.tasks.backends.dummy.DummyBackend",
            "QUEUES": settings.TASKS["default"]["QUEUES"],
        }
    }

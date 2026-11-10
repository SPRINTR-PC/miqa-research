import pytest


@pytest.fixture(autouse=True)
def _dummy_tasks_backend(settings):
    """Use Django's dummy task backend in tests only."""
    default_tasks = settings.TASKS.get("default", {})

    settings.TASKS = {
        **settings.TASKS,
        "default": {
            **default_tasks,
            "BACKEND": "django.tasks.backends.dummy.DummyBackend",
        },
    }


@pytest.fixture(scope="session")
def rustfs_endpoint():
    """Endpoint of the dev-test RustFS service for the real-S3 tests, starting it if it doesn't exist."""
    from tests.rustfs_service import ensure_rustfs_endpoint

    return ensure_rustfs_endpoint()

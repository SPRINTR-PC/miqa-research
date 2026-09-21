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

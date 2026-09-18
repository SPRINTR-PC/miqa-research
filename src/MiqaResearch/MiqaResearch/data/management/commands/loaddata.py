from pathlib import Path

from django.conf import settings
from django.core.management.base import CommandError
from django.core.management.commands.loaddata import Command as LoadDataCommand

from MiqaResearch.data.fixtures.consent_data import write_django_fixture

CONSENT_DATA_GENERATOR_LABEL = "consent_data.py"


# Override the default loaddata command to prevent loading fixtures in production as the fixtures in this project are
# dev/test-only data.
class Command(LoadDataCommand):
    def handle(self, *fixture_labels, **options):
        if not settings.DEBUG:
            raise CommandError("loaddata is disabled outside DEBUG — fixtures in this project are dev/test-only data.")

        fixture_labels = self._resolve_consent_data(fixture_labels)

        return super().handle(*fixture_labels, **options)

    @staticmethod
    def _resolve_consent_data(fixture_labels):
        """Replace a "consent_data.py" label with a freshly generated consent_data.json fixture."""
        if not any(Path(label).name == CONSENT_DATA_GENERATOR_LABEL for label in fixture_labels):
            return fixture_labels

        generated_fixture_path = write_django_fixture(hash_key=settings.SENSITIVE_DATA_HASH_KEY)
        return tuple(
            str(generated_fixture_path) if Path(label).name == CONSENT_DATA_GENERATOR_LABEL else label
            for label in fixture_labels
        )

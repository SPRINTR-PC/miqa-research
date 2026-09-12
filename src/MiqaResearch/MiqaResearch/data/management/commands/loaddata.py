from django.conf import settings
from django.core.management.base import CommandError
from django.core.management.commands.loaddata import Command as LoadDataCommand


# Override the default loaddata command to prevent loading fixtures in production as the fixtures in this project are
# dev/test-only data.
class Command(LoadDataCommand):
    def handle(self, *fixture_labels, **options):
        if not settings.DEBUG:
            raise CommandError("loaddata is disabled outside DEBUG — fixtures in this project are dev/test-only data.")
        return super().handle(*fixture_labels, **options)

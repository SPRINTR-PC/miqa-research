from django.apps import AppConfig
from django.core import checks


class DocumentationConfig(AppConfig):
    name = "documentation"
    verbose_name = "Manuals"

    def ready(self):
        from documentation.checks import check_manual_builds

        checks.register(check_manual_builds)

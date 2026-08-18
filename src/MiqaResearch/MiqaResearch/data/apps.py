from django.apps import AppConfig
from django.db.utils import OperationalError, ProgrammingError


class DataConfig(AppConfig):
    name = "MiqaResearch.data"

    def ready(self):
        from MiqaResearch.data.models import OIDCRoleMapping

        try:
            OIDCRoleMapping.objects.seed_from_env(only_if_empty=True)
        except (OperationalError, ProgrammingError):
            pass

from django.apps import AppConfig
from django.db.models.signals import post_migrate


def _seed_oidc_role_mappings(sender, **kwargs):
    from MiqaResearch.data.models import OIDCRoleMapping

    OIDCRoleMapping.objects.seed_from_env(only_if_empty=True)


class DataConfig(AppConfig):
    name = "MiqaResearch.data"

    def ready(self):
        from MiqaResearch.data import signals  # noqa: F401

        post_migrate.connect(
            _seed_oidc_role_mappings, sender=self, dispatch_uid="data.seed_oidc_role_mappings"
        )

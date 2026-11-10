import django.db.models.deletion
from django.db import migrations, models

# (model, related_name)
LINKED = [
    ("etllocationgrant", "location_grants"),
    ("etlsourcelocation", "source_locations"),
    ("pipelinebinding", "pipeline_bindings"),
]


def create_default_storage(apps, schema_editor):
    """The Default storage is the platform-wide MIRES_ETL_S3_* settings (read live at use time), so
    an existing deployment behaves exactly as before."""
    EtlStorage = apps.get_model("data", "EtlStorage")
    default, _ = EtlStorage.objects.get_or_create(name="Default", defaults={"is_default": True})
    for model_name, _related in LINKED:
        apps.get_model("data", model_name).objects.filter(storage__isnull=True).update(storage=default)


class Migration(migrations.Migration):

    dependencies = [
        ("data", "0038_etl_storage"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="etlsourcelocation", name="mires_etl_source_location_project_bucket_prefix"),
        migrations.AlterUniqueTogether(name="etllocationgrant", unique_together=set()),
        migrations.AlterUniqueTogether(name="pipelinebinding", unique_together=set()),
        *[
            migrations.AddField(
                model_name=model_name, name="storage",
                field=models.ForeignKey(
                    null=True, on_delete=django.db.models.deletion.PROTECT, related_name=related,
                    to="data.etlstorage"))
            for model_name, related in LINKED
        ],
        migrations.RunPython(create_default_storage, migrations.RunPython.noop),
        *[
            migrations.AlterField(
                model_name=model_name, name="storage",
                field=models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT, related_name=related, to="data.etlstorage"))
            for model_name, related in LINKED
        ],
        migrations.AlterUniqueTogether(
            name="etllocationgrant", unique_together={("project", "storage", "bucket", "prefix")}),
        migrations.AlterUniqueTogether(
            name="pipelinebinding", unique_together={("storage", "source_bucket", "source_prefix")}),
        migrations.AddConstraint(
            model_name="etlsourcelocation",
            constraint=models.UniqueConstraint(
                fields=("project", "storage", "bucket", "prefix"),
                name="mires_etl_source_location_project_bucket_prefix")),
    ]

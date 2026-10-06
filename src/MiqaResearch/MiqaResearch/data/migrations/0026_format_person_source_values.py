"""Rewrites every stored Study Participant identifier into the shared format (trimmed, dashes
removed) that consent loads and DICOM ingestion now both use (#241). Aborts, changing nothing, if
two participants of one project would end up with the same identifier -- merge those by hand first.
Not reversible: the original spelling isn't kept."""
from django.db import migrations

from helpers.person_source_value import reformat_stored_person_source_values


def format_person_source_values(apps, schema_editor):
    reformat_stored_person_source_values(apps.get_model("data", "StudyParticipant"))


class Migration(migrations.Migration):

    dependencies = [
        ('data', '0025_etlscriptversion_config_schema'),
    ]

    operations = [
        migrations.RunPython(format_person_source_values, reverse_code=migrations.RunPython.noop),
    ]

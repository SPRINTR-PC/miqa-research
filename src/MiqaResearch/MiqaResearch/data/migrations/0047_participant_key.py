import uuid

import django.db.models.deletion
from django.db import migrations, models

import helpers.db_fields


def add_legacy_keys(apps, schema_editor):
    """One synthetic `legacy:participant` key per participant that has Studies (dev databases only)."""
    DicomStudy = apps.get_model("data", "DicomStudy")
    ParticipantKey = apps.get_model("data", "ParticipantKey")
    StudyParticipant = apps.get_model("data", "StudyParticipant")
    participant_ids = DicomStudy.objects.values_list("study_participant_id", flat=True).distinct()
    for participant in StudyParticipant.objects.filter(pk__in=participant_ids):
        if participant.research_project_id is None:
            raise RuntimeError(
                f"Participant {participant.alias1} has Dicom Studies but no Research Project; "
                "assign one before migrating.")
        key = ParticipantKey.objects.create(
            project_id=participant.research_project_id,
            key_type="legacy:participant",
            value=str(participant.pk),
            study_participant=participant,
            linked_via="legacy",
        )
        DicomStudy.objects.filter(study_participant=participant).update(participant_key=key)


class Migration(migrations.Migration):

    dependencies = [
        ("data", "0046_etljob_sandbox_image_manifest"),
    ]

    operations = [
        migrations.CreateModel(
            name="ParticipantKey",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid7, editable=False, primary_key=True, serialize=False)),
                ("key_type", models.CharField(help_text="`<source>:<attribute>`, e.g. dicom:PatientID", max_length=100)),
                ("value", helpers.db_fields.SearchableEncryptedCharField(hash_field_name="value_hash", help_text="Trimmed, case preserved", max_length=500)),
                ("value_hash", models.CharField(blank=True, db_index=True, editable=False, max_length=64, null=True)),
                ("linked_via", models.CharField(blank=True, choices=[("match", "Matched at ingest"), ("datatype", "participant_key_link Datatype"), ("admin", "Admin"), ("legacy", "Migrated legacy")], default="", max_length=10)),
                ("linked_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("first_seen_job", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="data.etljob")),
                ("linked_job", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="data.etljob")),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="participant_keys", to="data.researchproject")),
                ("study_participant", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="participant_keys", to="data.studyparticipant")),
            ],
            options={"db_table": "mires_participant_key"},
        ),
        migrations.AddConstraint(
            model_name="participantkey",
            constraint=models.UniqueConstraint(fields=("project", "key_type", "value_hash"), name="mires_participant_key_unique"),
        ),
        migrations.AddField(
            model_name="dicomstudy",
            name="participant_key",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to="data.participantkey"),
        ),
        migrations.RunPython(add_legacy_keys, migrations.RunPython.noop),
        migrations.RemoveField(model_name="dicomstudy", name="study_participant"),
        migrations.AlterField(
            model_name="dicomstudy",
            name="participant_key",
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="data.participantkey"),
        ),
    ]

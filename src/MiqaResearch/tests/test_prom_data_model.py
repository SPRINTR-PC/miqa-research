from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone

from MiqaResearch.data.management.commands.import_prom_form_template import DEFAULT_TEMPLATE_NAME
from MiqaResearch.data.models import ParsedPromForm, PromData, PromFormTemplate, ResearchProject

User = get_user_model()


@pytest.fixture
def prom_form_template(db):
    call_command("import_prom_form_template")
    return PromFormTemplate.objects.get(name=DEFAULT_TEMPLATE_NAME)


@pytest.fixture
def research_project(db):
    return ResearchProject.objects.create(name="Test project", description="Test project for model tests")


@pytest.fixture
def uploader(db):
    return User.objects.create_user(username="uploader", email="uploader@example.com", password="password")


@pytest.fixture
def prom_data(prom_form_template, research_project, uploader, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    return PromData.objects.create(
        project=research_project,
        prom_form_template=prom_form_template,
        prom_form_file=SimpleUploadedFile("scan.pdf", b"%PDF-1.4", content_type="application/pdf"),
        uploaded_by=uploader,
    )


@pytest.mark.django_db
def test_creating_prom_data_captures_the_templates_current_version(prom_data, prom_form_template):
    assert prom_data.template_version == prom_form_template.template.version


@pytest.mark.django_db
def test_creating_parsed_prom_form_populates_created_at_and_extraction_flags(prom_data):
    parsed = ParsedPromForm.objects.create(data={"data": [], "fieldsOutOfTolerance": []}, prom_file=prom_data)

    assert parsed.created_at is not None
    assert parsed.extraction_flags == {}


@pytest.mark.django_db
def test_latest_run_for_a_prom_data_is_ordered_by_created_at_not_validated_at(prom_data, uploader):
    older_but_validated = ParsedPromForm.objects.create(
        data={"data": [], "fieldsOutOfTolerance": []}, prom_file=prom_data
    )
    newer_but_unreviewed = ParsedPromForm.objects.create(
        data={"data": [], "fieldsOutOfTolerance": []}, prom_file=prom_data
    )

    # A human reviewed the OLDER run after the NEWER run had already landed --
    # the old Meta.ordering = ["-validated_at"] would have put this one first.
    ParsedPromForm.objects.filter(pk=older_but_validated.pk).update(created_at=timezone.now() - timedelta(days=1))
    older_but_validated.validated_by = uploader
    older_but_validated.validated_at = timezone.now()
    older_but_validated.save()

    latest = ParsedPromForm.objects.filter(prom_file=prom_data).first()

    assert latest.pk == newer_but_unreviewed.pk


@pytest.mark.django_db(transaction=True)
def test_migration_0007_backfills_template_version_for_pre_existing_prom_data():
    app_label = "data"
    pre_migration_target = [(app_label, "0006_alter_promformtemplate_options_and_more")]
    post_migration_target = [(app_label, "0007_alter_parsedpromform_options_and_more")]
    restore_targets = MigrationExecutor(connection).loader.graph.leaf_nodes()

    try:
        old_state = MigrationExecutor(connection).migrate(pre_migration_target)

        OldFormTemplate = old_state.apps.get_model("kpforms", "FormTemplate")
        OldPromFormTemplate = old_state.apps.get_model(app_label, "PromFormTemplate")
        OldResearchProject = old_state.apps.get_model(app_label, "ResearchProject")
        OldPromData = old_state.apps.get_model(app_label, "PromData")
        OldUser = old_state.apps.get_model(User._meta.app_label, User._meta.model_name)

        form_template = OldFormTemplate.objects.create(name="Pre-migration template", schema={}, version=3)
        prom_form_template = OldPromFormTemplate.objects.create(
            name="Pre-migration PromFormTemplate", template=form_template, published=True
        )
        project = OldResearchProject.objects.create(name="Pre-migration project", description="Pre-migration")
        user = OldUser.objects.create_user(username="pre-migration-uploader", password="password")
        old_prom_data = OldPromData.objects.create(
            project=project,
            prom_form_template=prom_form_template,
            prom_form_file="scans/pre-migration.pdf",
            uploaded_by=user,
        )

        new_state = MigrationExecutor(connection).migrate(post_migration_target)

        NewPromData = new_state.apps.get_model(app_label, "PromData")
        migrated = NewPromData.objects.get(pk=old_prom_data.pk)
        assert migrated.template_version == 3
    finally:
        MigrationExecutor(connection).migrate(restore_targets)

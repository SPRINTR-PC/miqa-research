import json

import pytest
from django.core.management import call_command
from kpforms.form_schema import FormTemplateSchema
from kpforms.models import FormTemplate

from MiqaResearch.data.management.commands.import_prom_form_template import (
    DEFAULT_TEMPLATE_NAME,
    DEFAULT_TEMPLATE_PATH,
)
from MiqaResearch.data.models import PromFormTemplate


def test_template_file_round_trips_through_form_template_schema():
    raw_schema = json.loads(DEFAULT_TEMPLATE_PATH.read_text(encoding="utf-8"))

    validated = FormTemplateSchema(**raw_schema)

    all_fields = [field for section in validated.sections for group in section.inputGroups for field in group.fields]
    assert len(all_fields) > 0
    assert all(field.required is False for field in all_fields)
    assert all(field.predefinedValue is False for field in all_fields)


@pytest.mark.django_db
def test_command_creates_form_template_from_default_file():
    call_command("import_prom_form_template")

    template = FormTemplate.objects.get(name=DEFAULT_TEMPLATE_NAME)
    assert template.schema["title"]
    assert len(template.schema["sections"]) == 3
    assert PromFormTemplate.objects.filter(name=DEFAULT_TEMPLATE_NAME).exists()


@pytest.mark.django_db
def test_command_is_idempotent_by_name():
    call_command("import_prom_form_template")
    call_command("import_prom_form_template")

    assert FormTemplate.objects.filter(name=DEFAULT_TEMPLATE_NAME).count() == 1


@pytest.mark.django_db
def test_command_accepts_a_custom_name():
    call_command("import_prom_form_template", name="Custom PROM Template Name")

    assert FormTemplate.objects.filter(name="Custom PROM Template Name").exists()
    assert not FormTemplate.objects.filter(name=DEFAULT_TEMPLATE_NAME).exists()

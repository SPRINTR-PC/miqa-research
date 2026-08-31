import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from kpforms.form_schema import CreateFormTemplateSchema, FormTemplateSchema
from kpforms.helpers import create_form_template
from kpforms.models import FormTemplate
from pydantic import ValidationError

from MiqaResearch.data.models.prom_data import PromFormTemplate

DEFAULT_TEMPLATE_PATH = (
    settings.BASE_DIR / "tests" / "example_data" / "prom_data" / "templates" / "PROM_1_PRO_GI_GU_SWE.json"
)
DEFAULT_TEMPLATE_NAME = "PROM GI-GU SWE"


class Command(BaseCommand):
    help = "Import a PROM kpforms FormTemplate from a template JSON file. Idempotent by name."

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            default=str(DEFAULT_TEMPLATE_PATH),
            help=f"Path to the FormTemplateSchema JSON file (default: {DEFAULT_TEMPLATE_PATH}).",
        )
        parser.add_argument(
            "--name",
            default=DEFAULT_TEMPLATE_NAME,
            help=f"Name to give the FormTemplate (default: {DEFAULT_TEMPLATE_NAME!r}).",
        )
        parser.add_argument(
            "--description",
            default=None,
            help="Optional description for the FormTemplate.",
        )

    def handle(self, *args, **options):
        template_path = Path(options["file"])
        name = options["name"]

        if FormTemplate.objects.filter(name=name, deleted=None).exists():
            self.stdout.write(self.style.WARNING(f"FormTemplate {name!r} already exists, skipping import."))
            return

        try:
            raw_schema = json.loads(template_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise CommandError(f"Template file not found: {template_path}")
        except json.JSONDecodeError as e:
            raise CommandError(f"Template file is not valid JSON: {e}")

        try:
            form_schema = FormTemplateSchema(**raw_schema)
        except ValidationError as e:
            raise CommandError(f"Template file does not match FormTemplateSchema: {e}")

        template = create_form_template(
            CreateFormTemplateSchema(name=name, description=options["description"], formSchema=form_schema),
            user=None,
        )

        prom_template = PromFormTemplate.objects.create(
            name=name,
            template=template,
            project_specific=None,
            published=True,
        )
        self.stdout.write(self.style.SUCCESS(f"Created FormTemplate {prom_template.name!r} (id={prom_template.id})."))

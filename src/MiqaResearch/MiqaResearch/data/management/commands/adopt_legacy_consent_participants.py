from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from MiqaResearch.data.models import ParticipantConsent, ResearchProject, StudyParticipant


class Command(BaseCommand):
    help = (
        "Adopt every Legacy Consent Participant (no project, but a consent of a Consent Project type) into "
        "the Consent Project (MIRES_TASK_CONSENT_RESEARCH_PROJECT_NAME). Run once before the first ETL "
        "consent import: the participant_consent Datatype matches participants per project and would "
        "otherwise create duplicates (#241). Idempotent."
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Report how many would be adopted; change nothing.")

    def handle(self, *args, **options):
        if not (project_name := settings.TASK_CONSENT_RESEARCH_PROJECT_NAME):
            raise CommandError("MIRES_TASK_CONSENT_RESEARCH_PROJECT_NAME is not set.")
        try:
            project = ResearchProject.objects.get(name=project_name)
        except ResearchProject.DoesNotExist:
            raise CommandError(f"Research project {project_name!r} does not exist.") from None

        legacy_participants = StudyParticipant.objects.filter(
            research_project__isnull=True,
            id__in=ParticipantConsent.objects.filter(
                consent_type__research_project=project).values("study_participant_id"),
        )
        if options["dry_run"]:
            self.stdout.write(f"Would adopt {legacy_participants.count()} participant(s) into {project_name!r}.")
            return
        adopted = legacy_participants.update(research_project=project)
        self.stdout.write(self.style.SUCCESS(f"Adopted {adopted} participant(s) into {project_name!r}."))

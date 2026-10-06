from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Exists, OuterRef

from MiqaResearch.data.models import ParticipantConsent, ResearchProject, StudyParticipant


class Command(BaseCommand):
    help = (
        "Adopt every Legacy Consent Participant (no project, but a consent of a Consent Project type) into "
        "the Consent Project (MIRES_TASK_CONSENT_RESEARCH_PROJECT_NAME). Run once before the first ETL "
        "consent import: the participant_consent Datatype matches participants per project and would "
        "otherwise create duplicates (#241). A Legacy Consent Participant whose person is already in the "
        "Consent Project is skipped and listed by alias1, for manual merging. Idempotent."
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

        same_person_in_project = StudyParticipant.objects.filter(
            research_project=project, person_source_value_hash=OuterRef("person_source_value_hash"))
        candidates = StudyParticipant.objects.filter(
            research_project__isnull=True,
            id__in=ParticipantConsent.objects.filter(
                consent_type__research_project=project).values("study_participant_id"),
        ).annotate(collides=Exists(same_person_in_project))

        for legacy in candidates.filter(collides=True).order_by("alias1"):
            in_project = StudyParticipant.objects.filter(
                research_project=project, person_source_value_hash=legacy.person_source_value_hash)
            self.stdout.write(self.style.WARNING(
                f"Skipped {legacy.alias1!r}: the same person is already in {project_name!r} as "
                f"{', '.join(repr(alias) for alias in in_project.values_list('alias1', flat=True))}. Merge by hand."))

        adoptable = candidates.filter(collides=False)
        if options["dry_run"]:
            self.stdout.write(f"Would adopt {adoptable.count()} participant(s) into {project_name!r}.")
            return
        adopted = StudyParticipant.objects.filter(id__in=adoptable.values("id")).update(research_project=project)
        self.stdout.write(self.style.SUCCESS(f"Adopted {adopted} participant(s) into {project_name!r}."))

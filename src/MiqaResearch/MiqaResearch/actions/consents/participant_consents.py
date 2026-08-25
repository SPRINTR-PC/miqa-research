import logging

from django.conf import settings

from MiqaResearch.data.models import Clinic, ParticipantConsent, ParticipantConsentType, ResearchProject
from MiqaResearch.data.serializers.participant_consent import UploadConsentSchema

logger = logging.getLogger(__name__)

async def create_participant_consents(new_consents: list[UploadConsentSchema]) -> tuple[int, int]:
    total_consent_count = sum(1 for new_consent in new_consents for _ in new_consent.consent_labels)
    logger.info(f"Going through list of {total_consent_count} consents to upsert into database.")

    unique_consent_labels = {
        consent_label: None
        for consent in new_consents
        for consent_label in consent.consent_labels
    }.keys()

    participant_consent_types: dict[str, ParticipantConsentType] = {}
    new_consent_type_count = 0
    default_research_project = None
    for label in unique_consent_labels:
        try:
            consent_type = await ParticipantConsentType.objects.aget(label=label)
        except ParticipantConsentType.DoesNotExist:
            if default_research_project is None:
                default_research_project = await _get_default_research_project()
            consent_type = await ParticipantConsentType.objects.acreate(
                label=label, research_project=default_research_project)
            new_consent_type_count += 1
        participant_consent_types[label] = consent_type

    if new_consent_type_count:
        logger.debug(f"Created {new_consent_type_count} new participant consent types")

    logger.debug("Starting to upsert participant consents in db")
    new_consent_count = 0
    for consent in new_consents:
        clinic, _ = await Clinic.objects.aget_or_create(clinic_name=consent.clinic)
        for consent_label in consent.consent_labels:
            _, created = await ParticipantConsent.objects.aget_or_create(
                study_participant_id=consent.participant_study_id,
                consent_type=participant_consent_types[consent_label],
                consent_signed_date=consent.signed_date.date(),
                defaults={
                    "status": consent.status,
                    "clinic": clinic,
                    "consent_revoked_date": consent.retracted.date() if consent.retracted else None,
                    "extra_info": consent.extra_info,
                },
            )
            new_consent_count += created

    logger.info(f"Created {new_consent_count} new participant consents")

    return new_consent_count, total_consent_count - new_consent_count


async def _get_default_research_project() -> ResearchProject:
    project_name = settings.TASK_CONSENT_RESEARCH_PROJECT_NAME
    if not project_name:
        raise ValueError(
            "MIRES_TASK_CONSENT_RESEARCH_PROJECT_NAME must be set to create new participant consent types.")

    research_project, _ = await ResearchProject.objects.aget_or_create(
        name=project_name,
        defaults={"description": f"Research project for consent forms imported via the {project_name} consent task."},
    )
    return research_project

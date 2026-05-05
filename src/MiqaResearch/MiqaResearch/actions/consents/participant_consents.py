import logging

from MiqaResearch.data.models import ParticipantConsent, ParticipantConsentType, StudyParticipant, ResearchProject
from MiqaResearch.data.serializers.participant_consent import UploadConsentSchema

logger = logging.getLogger(__name__)

def create_participant_consents(new_consents: list[UploadConsentSchema]) -> tuple[int, int]:
    total_consent_count = sum(1 for new_consent in new_consents for _ in new_consent.consent_labels)
    logger.info(f"Going through list of {total_consent_count} consents to upsert into database.")

    participant_consent_types: dict[str, dict[str, ParticipantConsentType | ResearchProject | bool]] = {
        label: {
            "consent_type": (consent_type := ParticipantConsentType.objects.get_or_create(label=label))[0],
            "research_study": consent_type[0].research_project,
            "created": consent_type[1]
        }
        for label, _ in {
            consent_label: None
            for consent in new_consents
            for consent_label in consent.consent_labels
        }.items()
    }

    if (new_consent_type_count := sum(
            1
            for _, consent_type in participant_consent_types.items()
            if consent_type["created"] == True)
    ):
        logger.debug(f"Created {new_consent_type_count} new participant consent types")

    logger.debug("Starting to upsert participant consents in db")
    consents = [
        ParticipantConsent.objects.get_or_create(
            study_participant=StudyParticipant.objects.get_or_create(
                study_id=consent.participant_study_id,
                research_project=participant_consent_types[consent_label]["research_study"],
            ),
            consent_type=participant_consent_types[consent_label]["consent_type"],
            consent_start_date=consent.start_date,
            defaults={"consent_end_date": consent.end_date},
        )
        for consent in new_consents
        for consent_label in consent.consent_labels
    ]

    new_consent_count = sum(1 for consent in consents if consent[1])
    logger.info(f"Created {new_consent_count} new participant consents")

    return new_consent_count, total_consent_count - new_consent_count

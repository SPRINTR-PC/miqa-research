from itertools import groupby

from MiqaResearch.data.models import StudyParticipant


def upsert_study_participants(participant_id_name_list: tuple[str, str]) -> dict[str, StudyParticipant]:
    """
    Upserts study participants based on provided IDs. Generates a study participant ID if the person does not exist.

    Args:
        participant_id_name_list (tuple[str, str]): Tuple containing participant ID and name to upsert.

    Returns:
        dict[str, StudyParticipant]: Dictionary mapping participant IDs to upserted StudyParticipant instances.
    """
    # Make sure the participant IDs are normalised and unique
    participant_id_name_list = [
        next(g) for _, g in groupby([
            (
                participant[0].replace("-", ""),
                participant[1]
            )
            for participant in participant_id_name_list
            ], key=lambda x: x[0])
    ]

    # Get a dictionary of existing participants by their IDs
    existing_participants = {
        participant.person_source_value: participant
        for participant in StudyParticipant.objects.filter_by_person_source_value_list(
            person_source_values=[el[0] for el in participant_id_name_list]
        ).all()
    }

    # Create a list of participants that do not yet exist in the database and bulk create them,
    # then add them to a dictionary over newly created study participant instances.
    new_participants = {
        participant.person_source_value: participant
        for participant in StudyParticipant.objects.bulk_create([
            StudyParticipant(
                person_source_value=participant_id_name_list[0],
                name=participant_id_name_list[1],
            )
            for participant_id_name_list in participant_id_name_list
            if participant_id_name_list[0] not in existing_participants.keys()
        ])
    }

    return existing_participants | new_participants

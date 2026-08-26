from django.db.models import QuerySet

from MiqaResearch.data.models import StudyParticipant


async def get_list_of_study_participants_with_alias1_in_list_of_aliases(aliases: list[str]) -> list[str]:
    """Fetches a list of study participants whose alias1 is in the provided list of aliases.

    Args:
        aliases (list[str]): A list of aliases to search for.

    Returns:
        list[str]: A list of alias1 values of StudyParticipant objects whose alias1 is in the provided list of aliases.
    """
    return [
        el
        async for el in (
            StudyParticipant.objects
            .filter(alias1__in=aliases)
            .values_list("alias1", flat=True)
            .aiterator()
        )
    ]

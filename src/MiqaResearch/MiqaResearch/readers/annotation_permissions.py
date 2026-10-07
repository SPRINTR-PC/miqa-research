"""Who may author, supersede and retire Annotations and Segmentations (ADR 0026, #287).

- Authoring: Annotator, PI, Site PI and Admin, within Participant Visibility of that role row
  (a Site PI only at its Sites).
- Changing (Supersede, Retire): the author, while still an authoring role for the participant;
  PI, Site PI (its Sites) and Admin on anyone's work, ingested work included.

Both narrow the one Participant Visibility rule to role rows, so no Site logic lives here.
"""
from contract.constants.research_project_role import (
    PROJECT_ROLE_ADMIN,
    PROJECT_ROLE_ANNOTATOR,
    PROJECT_ROLE_PI,
    PROJECT_ROLE_SITE_PI,
)
from MiqaResearch.readers.participant_visibility import can_see_participant

AUTHOR_ROLES = (PROJECT_ROLE_ANNOTATOR, PROJECT_ROLE_PI, PROJECT_ROLE_SITE_PI, PROJECT_ROLE_ADMIN)
OVERSEER_ROLES = (PROJECT_ROLE_PI, PROJECT_ROLE_SITE_PI, PROJECT_ROLE_ADMIN)


class ParticipantRights:
    """One user's Annotation/Segmentation rights on one participant (two queries, then pure)."""

    def __init__(self, user, project, participant):
        self.user_id = user.pk
        self.can_author = can_see_participant(user, project, participant, AUTHOR_ROLES)
        self.is_overseer = can_see_participant(user, project, participant, OVERSEER_ROLES)

    def can_change(self, author_id) -> bool:
        """Whether the user may supersede or retire a chain whose head was authored by `author_id`."""
        return self.is_overseer or (self.can_author and author_id is not None and author_id == self.user_id)

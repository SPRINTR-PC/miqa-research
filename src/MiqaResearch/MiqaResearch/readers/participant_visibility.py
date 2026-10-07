"""Participant Visibility (#272, decided in #179): the single rule for which Study Participants of a
Research Project a user may see. The data panel, participant view, viewer and WADO all go through
`visible_participants` / `can_see_participant`; nothing else computes visibility.

Rule:
- Superuser sees every participant of the project.
- Admin ("Project Admin") and PI see all Sites, whatever clinic is on their role row (there the
  clinic is only a Site Assignment).
- Any other role row: clinic=null means all Sites; a set clinic means participants with a consent
  (active or revoked) at that Site, counting only this project's consent types.
- A user's visibility is the union of their role rows. No role row on the project: nothing.

Everything is lazy (no query until evaluated), so `visible_participants` composes as a subquery,
e.g. `Exists(visible_participants(u, p).filter(pk=OuterRef(...)))`. The per-Site check is a live
`EXISTS` on `ParticipantConsent(clinic, study_participant)`; there is no caching.
"""
from django.db.models import Exists, OuterRef, Q, QuerySet

from MiqaResearch.data.models import ParticipantConsent, ResearchProjectUserRoleMap, StudyParticipant
from contract.constants.research_project_role import PROJECT_ROLE_ADMIN, PROJECT_ROLE_PI

ALL_SITES_ROLES = (PROJECT_ROLE_ADMIN, PROJECT_ROLE_PI)


def visible_participants(user, project, roles=None) -> QuerySet[StudyParticipant]:
    """Study Participants of `project` (instance or pk) that `user` may see, as a lazy QuerySet.

    `roles` (role names) narrows the rule to those role rows only, e.g. "participants this user
    may author Annotations on" (#287). A superuser is not narrowed.
    """
    participants = StudyParticipant.objects.filter(research_project=project)
    if not getattr(user, "is_authenticated", False):
        return participants.none()
    if user.is_superuser:
        return participants

    role_rows = ResearchProjectUserRoleMap.objects.filter(user=user, project=project)
    if roles is not None:
        role_rows = role_rows.filter(role__name__in=roles)
    all_sites = role_rows.filter(Q(role__name__in=ALL_SITES_ROLES) | Q(clinic__isnull=True))
    consent_at_own_site = ParticipantConsent.objects.filter(
        study_participant=OuterRef("pk"),
        consent_type__research_project=project,
        clinic__in=role_rows.filter(clinic__isnull=False).values("clinic"),
    )
    return participants.filter(Exists(all_sites) | Exists(consent_at_own_site))


def can_see_participant(user, project, participant, roles=None) -> bool:
    """Whether `user` may see `participant` (instance or pk) of `project` (through `roles` only, if given)."""
    participant_pk = getattr(participant, "pk", participant)
    return visible_participants(user, project, roles).filter(pk=participant_pk).exists()

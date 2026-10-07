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

Machine clients (ADR 0027) have no user: `participants_visible_to_client` applies the same rule to a
client-credentials Application through its Client Binding, as one role row with the binding's Site.

Everything is lazy (no query until evaluated), so `visible_participants` composes as a subquery,
e.g. `Exists(visible_participants(u, p).filter(pk=OuterRef(...)))`. The per-Site check is a live
`EXISTS` on `ParticipantConsent(clinic, study_participant)`; there is no caching.
"""
from django.db.models import Exists, OuterRef, Q, QuerySet

from MiqaResearch.data.models import ClientBinding, ParticipantConsent, ResearchProjectUserRoleMap, StudyParticipant
from contract.constants.research_project_role import PROJECT_ROLE_ADMIN, PROJECT_ROLE_PI

ALL_SITES_ROLES = (PROJECT_ROLE_ADMIN, PROJECT_ROLE_PI)


def visible_participants(user, project, roles=None) -> QuerySet[StudyParticipant]:
    """Study Participants of `project` (instance or pk) that `user` may see, as a lazy QuerySet.

    `roles` (role names) narrows the rule to those role rows only, e.g. "participants this user
    may author Annotations on" (#287). A superuser is not narrowed.
    """
    return visible_participants_in_any_project(user, roles).filter(research_project=project)


def visible_participants_in_any_project(user, roles=None) -> QuerySet[StudyParticipant]:
    """Study Participants `user` may see, each judged against its own Research Project, as a lazy QuerySet.

    For callers that start from an object rather than a project (WADO starts from a DicomFile URL):
    `Exists(visible_participants_in_any_project(u).filter(pk=OuterRef("...study_participant")))`
    checks visibility inside the query that loads the object. `roles` as in `visible_participants`.
    """
    participants = StudyParticipant.objects.all()
    if not getattr(user, "is_authenticated", False):
        return participants.none()
    if user.is_superuser:
        return participants

    role_rows = ResearchProjectUserRoleMap.objects.filter(user=user, project=OuterRef("research_project"))
    own_site_role = {
        "clinic__researchprojectuserrolemap__user": user,
        "clinic__researchprojectuserrolemap__project": OuterRef("research_project"),
    }
    if roles is not None:
        role_rows = role_rows.filter(role__name__in=roles)
        own_site_role["clinic__researchprojectuserrolemap__role__name__in"] = roles
    all_sites = role_rows.filter(Q(role__name__in=ALL_SITES_ROLES) | Q(clinic__isnull=True))
    consent_at_own_site = ParticipantConsent.objects.filter(
        study_participant=OuterRef("pk"),
        consent_type__research_project=OuterRef("research_project"),
        **own_site_role,
    )
    return participants.filter(Exists(all_sites) | Exists(consent_at_own_site))


def can_see_participant(user, project, participant, roles=None) -> bool:
    """Whether `user` may see `participant` (instance or pk) of `project` (through `roles` only, if given)."""
    participant_pk = getattr(participant, "pk", participant)
    return visible_participants(user, project, roles).filter(pk=participant_pk).exists()


def participants_visible_to_client(application) -> QuerySet[StudyParticipant]:
    """Study Participants a client-credentials `application` may see, as a lazy QuerySet.

    Its Client Binding acts as one non-all-Sites role row on the bound project: no Site means every
    participant of the project, a Site means participants with a consent (active or revoked) at that
    Site, counting only the project's consent types. An unbound client sees nothing. Composes like
    `visible_participants_in_any_project` (an `Exists` over `pk=OuterRef(...)`), no query of its own.
    """
    consent_at_bound_site = ParticipantConsent.objects.filter(
        study_participant=OuterRef(OuterRef("pk")),
        clinic=OuterRef("clinic"),
        consent_type__research_project=OuterRef("research_project"),
    )
    binding = ClientBinding.objects.filter(
        application=application, research_project=OuterRef("research_project")
    ).filter(Q(clinic__isnull=True) | Exists(consent_at_bound_site))
    return StudyParticipant.objects.filter(Exists(binding))

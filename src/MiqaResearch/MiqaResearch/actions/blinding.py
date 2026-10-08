"""Turn Blinded Annotation on or off, and make a Blinding Reveal (ADR 0026, #288). Both are audited."""
from django.db import transaction

from contract.constants.audit_log import EVENT_TYPE_BLINDED_ANNOTATION_CHANGED, EVENT_TYPE_BLINDING_REVEAL
from contract.constants.research_project_role import PROJECT_ROLE_ADMIN, PROJECT_ROLE_PI
from MiqaResearch.data.models import AuditLog, ResearchProject, ResearchProjectUserRoleMap
from MiqaResearch.readers.annotation_reader import ParticipantNotVisible, visible_participant
from MiqaResearch.readers.blinding import (
    MAX_VIEWER_SESSIONS,
    REVEAL_SESSION_KEY,
    can_reveal,
    viewer_session_id,
)

FLAG_ROLES = (PROJECT_ROLE_PI, PROJECT_ROLE_ADMIN)


class BlindingError(Exception):
    """Base for refusals; the API maps each subclass to a status code."""


class NotFound(BlindingError):
    """Unknown project or participant, or not visible to the caller (never distinguished)."""


class NotAllowed(BlindingError):
    """Visible, but the caller's roles don't allow it."""


class NotBlinded(BlindingError):
    """A Blinding Reveal on a project without Blinded Annotation."""


class NoViewerSession(BlindingError):
    """A Blinding Reveal without a Viewer Session id: it would have nothing to be scoped to."""


def set_blinded_annotation(*, user, project_id, blinded: bool, request=None) -> ResearchProject:
    """PI and Project Admin (and superusers) turn the flag on or off at any time. Only real changes are audited."""
    with transaction.atomic():
        project = ResearchProject.objects.select_for_update().filter(pk=project_id).first()
        if project is None:
            raise NotFound()
        if not user.is_superuser:
            role_rows = ResearchProjectUserRoleMap.objects.filter(user=user, project=project)
            roles = set(role_rows.values_list("role__name", flat=True))
            if not roles:
                raise NotFound()
            if not roles.intersection(FLAG_ROLES):
                raise NotAllowed("only a PI or a Project Admin may change Blinded Annotation")
        if project.blinded_annotation == blinded:
            return project
        project.blinded_annotation = blinded
        project.blinding_epoch += 1  # ends every Blinding Reveal made so far
        project.save(update_fields=["blinded_annotation", "blinding_epoch"])
        AuditLog.objects.record(
            EVENT_TYPE_BLINDED_ANNOTATION_CHANGED, user=user, request=request, project=project,
            metadata={"blinded": blinded},
        )
    return project


def reveal_participant(*, user, participant_id, request) -> None:
    """A Blinding Reveal of one participant for this request's Viewer Session (PI, Site PI at its Sites, Admin)."""
    viewer = viewer_session_id(request)
    if viewer is None:
        raise NoViewerSession("a Blinding Reveal is made from the viewer")
    try:
        participant, project = visible_participant(user, participant_id)
    except ParticipantNotVisible:
        raise NotFound() from None
    if not project.blinded_annotation:
        raise NotBlinded("this project doesn't use Blinded Annotation")
    if not can_reveal(user, project, participant):
        raise NotAllowed("only a PI, a Site PI or an Admin may reveal others' work")
    remember_reveal(request.session, viewer, participant.pk, project.blinding_epoch)
    AuditLog.objects.record(
        EVENT_TYPE_BLINDING_REVEAL, user=user, request=request, project=project,
        metadata={"participant_id": str(participant.pk)},
    )


def remember_reveal(session, viewer: str, participant_id, epoch: int) -> None:
    """Keep the reveal under its Viewer Session; only the most recent MAX_VIEWER_SESSIONS opens are kept."""
    reveals = dict(session.get(REVEAL_SESSION_KEY, {}))
    opened = {**reveals.pop(viewer, {}), str(participant_id): epoch}
    kept = list(reveals.items())[-(MAX_VIEWER_SESSIONS - 1):]
    session[REVEAL_SESSION_KEY] = {**dict(kept), viewer: opened}

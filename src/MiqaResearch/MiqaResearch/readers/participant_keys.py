"""Reads on Participant Keys (ADR 0035) and the Data tab's key tracking view (#422)."""
from django.db.models import (
    BooleanField,
    CharField,
    Count,
    Exists,
    ExpressionWrapper,
    OuterRef,
    Q,
    QuerySet,
    Value,
)
from django.utils.translation import gettext

from contract.constants.research_project_role import PROJECT_ROLE_ADMIN
from MiqaResearch.data.models import ParticipantKey, ResearchProject, ResearchProjectUserRoleMap
from MiqaResearch.data.serializers.data_table_definition import (
    DataTableColumn,
    DataTableDefinition,
    DataTableFilter,
    DataTableSource,
)
from MiqaResearch.readers.participant_visibility import visible_participants

MASKED_VALUE = "********"


def participant_alias_of(key: ParticipantKey) -> str:
    """The pseudonym shown in de-identified output for the key's data: the Study Participant's `alias1`
    when linked, else a stable one from the key's id (nothing else is pseudonymous yet)."""
    participant = key.study_participant
    return participant.alias1 if participant is not None else f"UNLINKED-{key.pk.hex[:12]}"


def is_project_admin(user, project) -> bool:
    """Superuser or a project Admin: the only ones who may re-point or unlink."""
    if not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser:
        return True
    return ResearchProjectUserRoleMap.objects.filter(user=user, project=project, role__name=PROJECT_ROLE_ADMIN).exists()


def has_project_role(user, project) -> bool:
    """Superuser or any role on `project`."""
    return bool(user.is_superuser or ResearchProjectUserRoleMap.objects.filter(user=user, project=project).exists())


def project_with_role(user, project_id) -> ResearchProject | None:
    """The project, or None when it is unknown or `user` has no role on it (never told apart)."""
    project = ResearchProject.objects.filter(pk=project_id).first()
    return project if project is not None and has_project_role(user, project) else None


def key_with_role(user, key_id) -> ParticipantKey | None:
    """The key (with its project), or None when unknown or `user` has no role on its project."""
    key = ParticipantKey.objects.select_related("project").filter(pk=key_id).first()
    return key if key is not None and has_project_role(user, key.project) else None


def keys_visible_to(user, project) -> QuerySet[ParticipantKey]:
    """Keys of `project` the user's Participant Visibility allows: unlinked ones, and ones linked to a visible
    participant. Role gating (Admin / Data Manager) is the caller's, via `can_open_unlinked`."""
    visible = visible_participants(user, project).filter(pk=OuterRef("study_participant_id"))
    return ParticipantKey.objects.filter(project=project).filter(Q(study_participant__isnull=True) | Exists(visible))


def key_table_source(user, project, *, reveal: bool = False) -> DataTableSource:
    """The Participant Key table. The value is masked unless `reveal` (the caller audits that as an Identity Reveal)."""
    queryset = keys_visible_to(user, project).annotate(
        masked_value=Value(MASKED_VALUE, output_field=CharField()),
        linked=ExpressionWrapper(Q(study_participant__isnull=False), output_field=BooleanField()),
        study_count=Count("dicomstudy", distinct=True),
        series_count=Count("dicomstudy__dicomseries", distinct=True),
    )
    value_column = (
        DataTableColumn(
            "value", gettext("Value"), "string", filter=DataTableFilter("text-exact", hash_field="value_hash"))
        if reveal else DataTableColumn("masked_value", gettext("Value"), "string")
    )
    definition = DataTableDefinition(columns=(
        DataTableColumn("id", gettext("Key"), "string"),
        DataTableColumn("key_type", gettext("Type"), "string", sortable=True, filter=DataTableFilter("dropdown")),
        value_column,
        DataTableColumn("linked", gettext("Linked"), "boolean", sortable=True, filter=DataTableFilter("boolean")),
        DataTableColumn(
            "study_participant__alias1", gettext("Participant"), "string", sortable=True,
            filter=DataTableFilter("text")),
        DataTableColumn("study_count", gettext("Studies"), "number", sortable=True),
        DataTableColumn("series_count", gettext("Series"), "number", sortable=True),
        DataTableColumn(
            "created_at", gettext("First seen"), "datetime", sortable=True, default_sort="desc", default_sort_order=1),
    ))
    return DataTableSource(queryset.values(*definition.values_fields), definition)


def search_participants(user, project, query: str, limit: int = 20) -> list[dict]:
    """Visible participants of `project` whose alias contains `query`: id and alias only, no identity."""
    matches = visible_participants(user, project).filter(alias1__icontains=query.strip()).order_by("alias1")
    return [{"id": p.pk, "alias": p.alias1} for p in matches[:limit]]

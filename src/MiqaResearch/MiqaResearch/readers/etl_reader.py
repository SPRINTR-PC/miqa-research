"""Read-only queries backing the ETL Pipelines tab's Scripts/Bindings/Defaults sections (#158)."""
import logging
from pathlib import PurePath
from typing import NamedTuple

from asgiref.sync import sync_to_async
from django.db.models import Case, Count, F, Q, When
from django.utils.translation import gettext

from contract.constants.etl import ETL_SCRIPT_ORIGIN_CUSTOM, ETL_SCRIPT_ORIGIN_NATIVE
from MiqaResearch.data.models import (
    EtlJob,
    EtlJobInput,
    EtlLocationGrant,
    EtlProjectSettings,
    EtlScript,
    EtlScriptVersion,
    EtlSourceLocation,
    PipelineBinding,
    ResearchProject,
)
from MiqaResearch.data.serializers.data_table_definition import (
    DataTableColumn,
    DataTableDefinition,
    DataTableFilter,
    DataTableSource,
)

logger = logging.getLogger(__name__)


async def get_project_custom_scripts(project: ResearchProject) -> list[EtlScript]:
    """Custom scripts, each annotated with `version_count` so templates never need to lazily
    evaluate `.versions.all()` -- an async view can't run that DB query when rendering."""
    return [
        script async for script in
        EtlScript.objects.filter(project=project, origin=ETL_SCRIPT_ORIGIN_CUSTOM)
        .annotate(version_count=Count("versions"), **_config_schema_version_count())
    ]


async def get_project_custom_scripts_table_source(project: ResearchProject, *, can_edit: bool) -> DataTableSource:
    """The project's custom scripts as a Data Table source. `edit_id` is the script's id while it can be edited (the
    viewer may manage scripts and the script is not archived), else null, so the table shows no Edit button. The
    Datatype filter offers the datatypes in use, sorted alphabetically."""
    datatype_names = sorted({
        name async for name in
        EtlScript.objects.filter(project=project, origin=ETL_SCRIPT_ORIGIN_CUSTOM)
        .exclude(datatype_name="")
        .values_list("datatype_name", flat=True)
    })
    columns = [
        DataTableColumn("name", gettext("Name"), "string", sortable=True, default_sort="asc",
                        filter=DataTableFilter("text")),
        DataTableColumn("description", gettext("Description"), "string"),
        DataTableColumn("datatype_name", gettext("Datatype"), "string", sortable=True,
                        filter=DataTableFilter("dropdown", options=tuple((name, name) for name in datatype_names))),
        DataTableColumn("version_count", gettext("Versions"), "number", sortable=True),
    # DataTableColumn("config_schema_version_count", gettext("Versions with config schema"), "number", sortable=True),
        DataTableColumn("archived_at", gettext("Archived"), "datetime", sortable=True),
    ]
    if can_edit:
        columns.append(DataTableColumn("edit_id", "", "button", button_label=gettext("Edit")))
    definition = DataTableDefinition(columns=tuple(columns))
    queryset = (
        EtlScript.objects.filter(project=project, origin=ETL_SCRIPT_ORIGIN_CUSTOM)
        .annotate(
            version_count=Count("versions"),
            **_config_schema_version_count(),
            edit_id=Case(When(archived_at__isnull=True, then=F("id")), default=None),
        )
        .values(*definition.values_fields)
    )
    return DataTableSource(queryset, definition)


async def get_native_scripts() -> list[EtlScript]:
    return [
        script async for script in
        EtlScript.objects.filter(origin=ETL_SCRIPT_ORIGIN_NATIVE, archived_at__isnull=True)
        .annotate(**_config_schema_version_count())
    ]


def _config_schema_version_count() -> dict:
    """How many of a Script's Versions declare a config schema (#238)."""
    return {"config_schema_version_count": Count("versions", filter=Q(versions__config_schema__isnull=False))}


async def get_project_bindings(project: ResearchProject) -> list[PipelineBinding]:
    return [
        binding async for binding in
        PipelineBinding.objects.filter(project=project).select_related(
            "script_version", "script_version__script", "source_location")
    ]


async def get_project_jobs(project: ResearchProject) -> list[EtlJob]:
    """The project's Jobs, newest first, with their Binding and pinned Script Version preloaded
    for the Jobs panel. Each Job gets an `is_stuck` attribute: a "running" Job past its timeout
    plus grace (the orchestrator's stuck rule) displays as stuck before recovery sweeps it."""
    from django.utils import timezone

    from MiqaResearch.tasks.etl_orchestrator.stuck import is_stuck

    now = timezone.now()
    jobs = [
        job async for job in
        EtlJob.objects.filter(binding__project=project)
        .select_related("binding", "script_version", "script_version__script")
    ]
    for job in jobs:
        job.is_stuck = is_stuck(job, now)
    return jobs


async def get_project_job(project: ResearchProject, job_id) -> EtlJob | None:
    """One of the project's Jobs for its detail view, or None if `job_id` isn't this project's.
    Carries `is_stuck` like `get_project_jobs`, plus its inputs as `input_list` -- an async view
    can't lazily evaluate `.inputs.all()` while rendering."""
    from django.utils import timezone

    from MiqaResearch.tasks.etl_orchestrator.stuck import is_stuck

    job = await EtlJob.objects.filter(binding__project=project, id=job_id) \
        .select_related("binding", "script_version", "script_version__script").afirst()
    if job is None:
        return None
    job.is_stuck = is_stuck(job, timezone.now())
    job.input_list = [job_input async for job_input in EtlJobInput.objects.filter(job=job)]
    return job


async def get_project_location_grants(project: ResearchProject) -> list[EtlLocationGrant]:
    return [grant async for grant in EtlLocationGrant.objects.filter(project=project)]


async def get_project_source_locations(project: ResearchProject) -> list[EtlSourceLocation]:
    """The project's Source Locations (#268), each annotated with `binding_count`."""
    return [
        location async for location in
        EtlSourceLocation.objects.filter(project=project).annotate(binding_count=Count("bindings"))
    ]


async def get_bindable_script_versions(project: ResearchProject) -> list[EtlScriptVersion]:
    """Every Version of a usable Script for this project's binding wizard: native scripts (global)
    plus this project's own non-archived custom scripts. Archived scripts are excluded outright --
    an archived custom Script cannot be bound to a new pipeline."""
    return [
        version async for version in
        EtlScriptVersion.objects.filter(script__archived_at__isnull=True)
        .filter(Q(script__origin=ETL_SCRIPT_ORIGIN_NATIVE) | Q(script__project=project))
        .select_related("script")
        .order_by("script__name", "-version")
    ]


def script_version_choices(versions: list[EtlScriptVersion]) -> list[tuple[str, str]]:
    """(id, label) pairs for the binding wizard's Script & Version select -- built here rather than
    in a view/template so both the GET-render and the POST-validate side use the exact same list."""
    return [(str(version.id), f"{version.script.name} — v{version.version}") for version in versions]


def script_version_config_schemas(versions: list[EtlScriptVersion]) -> dict[str, dict | None]:
    """Each Version's config schema (#238), keyed like `script_version_choices`."""
    return {str(version.id): version.config_schema for version in versions}


async def get_project_settings(project: ResearchProject) -> EtlProjectSettings | None:
    return await EtlProjectSettings.objects.filter(project=project).afirst()


async def get_project_max_script_source_bytes(project: ResearchProject) -> int:
    """Async counterpart of `etl_project_settings.get_max_script_source_bytes` -- that helper runs
    a synchronous query, which an async view can't call directly."""
    from django.conf import settings as django_settings

    override = await EtlProjectSettings.objects.filter(project=project) \
        .values_list("max_script_source_bytes", flat=True).afirst()
    return override if override is not None else django_settings.ETL_SCRIPT_MAX_SOURCE_BYTES


def location_grant_allows(grants: list[EtlLocationGrant], bucket: str, prefix: str) -> bool:
    """Whether `bucket`/`prefix` falls within at least one of the project's `EtlLocationGrant`s.
    A grant with an empty prefix covers the whole bucket; otherwise the requested prefix must be
    that grant's prefix or a deeper path under it."""
    return any(
        grant.bucket == bucket and (grant.prefix == "" or prefix.startswith(grant.prefix))
        for grant in grants
    )


class LatestVersionDraft(NamedTuple):
    """What the "Add version" editors start from: the latest Version's code, its language
    extension (e.g. ".py") and its config schema (None when it declares none)."""
    code: str
    extension: str
    config_schema: dict | None


async def get_latest_version_code(script: EtlScript) -> LatestVersionDraft | None:
    """The latest Version's editable content, to prefill the editors when adding a Version (#393);
    None for a Script without versions, or whose source cannot be read."""
    latest = await script.versions.order_by("-version").afirst()
    if latest is None:
        return None

    def read() -> str:
        with latest.source.open("rb") as source:
            return source.read().decode(errors="replace")

    try:
        code = await sync_to_async(read)()
    except Exception:  # missing file, unreachable storage: prefill is a convenience, never fatal
        logger.warning("Could not read source of ETL script version %s for editor prefill", latest.id, exc_info=True)
        return None
    return LatestVersionDraft(code, PurePath(latest.source.name).suffix.lower(), latest.config_schema)

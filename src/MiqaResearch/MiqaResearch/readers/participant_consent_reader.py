import logging
from itertools import accumulate, chain, groupby
from operator import itemgetter
from typing import Any
from uuid import UUID

from django.db.models import (
    Count,
    F,
    IntegerField,
    OuterRef,
    Q,
    Subquery
)
from django.utils.translation import gettext
from ninja.errors import HttpError

from MiqaResearch.data.models import ParticipantConsent, ResearchProject
from MiqaResearch.data.serializers.charts.bar import (
    BarChartResponseSchema,
    BarChartConfigSchema,
    BarChartDataSchema,
    BarSeriesSchema,
)
from MiqaResearch.data.serializers.charts.base import ChartGroupingLabelsSchema, ChartGroupingSchema
from MiqaResearch.data.serializers.charts.xy import (
    FilledAreaChartResponseSchema,
    LineChartResponseSchema,
    XYChartDataSchema,
    XYSeriesSchema,
)
from MiqaResearch.data.serializers.data_table_definition import (
    DataTableColumn,
    DataTableDefinition,
    DataTableFilter,
    DataTableSource,
)
from MiqaResearch.data.serializers.participant_consent import (
    ClinicConsentHistorySchema,
    ConsentHistoryEventSchema,
    ProjectConsentHistoryByClinicSchema,
)
from MiqaResearch.readers.research_project_reader import (
    get_project_connected_clinics,
    get_user_project_connected_clinics,
    get_user_project_role_list,
)
from contract.constants.research_project_role import PROJECT_ROLE_ADMIN, PROJECT_ROLE_PI, \
    PROJECT_ROLE_PARTICIPANT_RECRUITER

logger = logging.getLogger("mires")

# Roles (besides superusers) that may view the consent table, see all clinics, and see participant identifiers (PID).
# Recruiters are clinic-scoped by the row filter. Eligibility for PID is decided here and only here.
CONSENT_TABLE_ROLES = (PROJECT_ROLE_ADMIN, PROJECT_ROLE_PI, PROJECT_ROLE_PARTICIPANT_RECRUITER)
CONSENT_TABLE_PROJECT_WIDE_ROLES = (PROJECT_ROLE_ADMIN, PROJECT_ROLE_PI)
CONSENT_TABLE_PID_ROLES = (PROJECT_ROLE_ADMIN, PROJECT_ROLE_PI, PROJECT_ROLE_PARTICIPANT_RECRUITER)


async def get_project_consent_count(project: ResearchProject) -> int:
    """
    Get the total count of active consents for a given project.
    """
    consent_counts = await ParticipantConsent.objects.filter(
        consent_type__research_project=project,
        consent_revoked_date__isnull=True
    ).acount()

    return consent_counts


async def get_project_consent_participant_count(project: ResearchProject) -> int:
    """
    Get the total count of particpants that have at least one active signed consentfor a given project.
    """
    participant_count = await ParticipantConsent.objects.filter(
        consent_type__research_project=project,
        consent_revoked_date__isnull=True
    ).order_by().values("study_participant_id").distinct().acount()

    return participant_count


async def get_consent_data_by_clinic(project: ResearchProject) -> ProjectConsentHistoryByClinicSchema:
    """
    Get consent data as a list grouped by clinic for a given project.
    """
    query = (
        ParticipantConsent.objects.filter(consent_type__research_project=project)
        .annotate(
            clinic_name=F("clinic__name"),
            consent_label=F("consent_type__label"),
            study_participant_alias=F("study_participant__alias1"),
            study_participant_pid=F("study_participant__person_source_value"),
            study_participant_name=F("study_participant__name"),
            study_participant_gender=F("study_participant__gender"),
        )
        .values(
            "id",
            "clinic_id",
            "clinic_name",
            "consent_type_id",
            "consent_label",
            "status",
            "consent_signed_date",
            "last_updated",
            "consent_revoked_date",
            "comment",
            "source",
            "study_participant_id",
            "study_participant_alias",
            "study_participant_pid",
            "study_participant_name",
            "study_participant_gender",
        )
    )


async def get_consent_history_by_clinic(request, project: ResearchProject) -> ProjectConsentHistoryByClinicSchema:
    """
    Get consent count history by clinic for a given project.
    """
    participant_consents_signed, participant_consents_revoked = await _get_consent_history_data(project)

    connected_clinics = await get_user_project_connected_clinics(request, project.id)

    formatted_data = _format_signed_retracted_data(
        signed_data=participant_consents_signed,
        retracted_data=participant_consents_revoked,
        clinics=connected_clinics
    )

    try:
        output = ProjectConsentHistoryByClinicSchema(
            project_id=project.id,
            consent_data_by_clinic=[
                ClinicConsentHistorySchema(
                    clinic_id=clinic["clinic_id"],
                    clinic_name=str(clinic["clinic_name"]),
                    consent_history=[ConsentHistoryEventSchema(**item) for item in formatted_data.get(clinic["clinic_id"], {})]
                )
                for clinic in connected_clinics
            ]
        )
    except Exception:
        logger.error("Failed to create output ProjectConsentHistoryByClinicSchema", exc_info=True)
        raise

    return output


async def get_consent_history_plot_by_clinic(project: ResearchProject) -> LineChartResponseSchema | FilledAreaChartResponseSchema:
    """
    Get consent count history plot data by clinic for a given project.
    """
    connected_clinics = await get_project_connected_clinics(project.id)

    formatted_data = await _get_consent_history_plot_data(project=project, clinics=connected_clinics)

    logger.info("Formatted consent history plot data for project %s", project.id)

    return LineChartResponseSchema(
        config=None,
        groupings=[
            ChartGroupingSchema(
                name=gettext("Consent History by Clinic"),
                label=gettext("Consent History by Clinic"),
                labels=ChartGroupingLabelsSchema(
                    x_axis_title=None,
                    y_axis_title=None,
                    legend_title=gettext("Clinic"),
                    y_axis_range=(0, None)
                ),
                data=formatted_data
            )
        ]
    )


async def get_consent_statistics_plot(project: ResearchProject) -> BarChartResponseSchema:
    """
    Get consent statistics plot data for a given project.
    """
    logger.debug("Querying for consent statistics")
    consents_per_clinic = [
        (clinic["clinic__clinic_name"], clinic["active_count"])
        async for clinic in (
            ParticipantConsent.objects
            .filter(
                consent_type__research_project=project,
                consent_revoked_date__isnull=True
            )
            .values("clinic_id", "clinic__clinic_name")
            .order_by("clinic__clinic_name")
            .annotate(
                active_count=Count("study_participant_id", distinct=True),
            )
        )
    ]

    consents_per_participant_information_version = [
        (row["participant_information_version"], row["active_count"])
        async for row in (
            ParticipantConsent.objects
            .filter(
                consent_type__research_project=project,
                consent_revoked_date__isnull=True
            )
            .values("participant_information_version")
            .annotate(
                active_count=Count("study_participant_id", distinct=True),
            )
        )
    ]

    consent_per_consent_type = [
        (short_label if (short_label := row["consent_type__short_label"]) else row["consent_type__label"],
         row["active_count"])
        async for row in (
            ParticipantConsent.objects
            .select_related("consent_type")
            .filter(
                consent_type__research_project=project,
                consent_revoked_date__isnull=True
            )
            .values("consent_type_id", "consent_type__label", "consent_type__short_label")
            .annotate(
                active_count=Count("study_participant_id", distinct=True),
            )
        )
    ]

    logger.debug("Creating data schema for clinic consents")
    consents_per_clinic_series = BarChartDataSchema(
        categories=[row[0] for row in consents_per_clinic],
        series=[BarSeriesSchema(name=gettext("Active Consents"), values=[row[1] for row in consents_per_clinic])]
    )
    logger.debug("Created data schema for clinic consents")

    logger.debug("Creating data schema for consents by PIV version")
    consents_per_piv_series = BarChartDataSchema(
        categories=[str(row[0]) if row[0] else gettext("Unknown") for row in consents_per_participant_information_version],
        series=[BarSeriesSchema(
            name=gettext("Active Consents"),
            values=[row[1] for row in consents_per_participant_information_version]
        )],
    )
    logger.debug("Created data schema for consents by PIV version")

    logger.debug("Creating data schema for consents by consent type")
    consents_per_consent_type = BarChartDataSchema(
        categories=[str(row[0]) for row in consent_per_consent_type],
        series=[BarSeriesSchema(name=gettext("Active Consents"), values=[row[1] for row in consent_per_consent_type])],
    )
    logger.debug("Created data schema for consents by consent type")

    logger.debug("Creating and returning BarChartResponseSchema for consent statistics")
    return BarChartResponseSchema(
        config=BarChartConfigSchema(bar_mode="stack", orientation="v"),
        groupings=[
            ChartGroupingSchema(
                name=gettext("Consent Statistics by Clinic"),
                label=gettext("Consent Statistics by Clinic"),
                labels=ChartGroupingLabelsSchema(x_axis_title=None, y_axis_title=None, legend_title=gettext("Clinic")),
                data=consents_per_clinic_series,
            ),
            ChartGroupingSchema(
                name=gettext("Consents By Consent Type"),
                label=gettext("Consents By Consent Type"),
                labels=ChartGroupingLabelsSchema(x_axis_title=None, y_axis_title=None, legend_title=gettext("Consent type")),
                data=consents_per_consent_type,
            ),
            ChartGroupingSchema(
                name=gettext("Consents by Participant Information Version"),
                label=gettext("Consents by Participant Information Version"),
                labels=ChartGroupingLabelsSchema(x_axis_title=None, y_axis_title=None, legend_title=gettext("Version")),
                data=consents_per_piv_series,
            ),
        ],
    )


async def user_can_view_consent_pid(user, project: ResearchProject) -> bool:
    """
    Whether the user may include participant identifiers (PID) in the consent table for the project.
    """
    if user.is_superuser:
        return True
    user_roles = await get_user_project_role_list(user, project)
    return not {user_role["name"] for user_role in user_roles}.isdisjoint(CONSENT_TABLE_PID_ROLES)


async def get_consent_table_data_for_project(
        project: ResearchProject, user, include_pid: bool = False) -> DataTableSource:
    user_roles = await get_user_project_role_list(user, project)

    user_role_names = {user_role["name"] for user_role in user_roles}

    if not user.is_superuser and user_role_names.isdisjoint(CONSENT_TABLE_ROLES):
        logger.error("Table data requested for research project the user does not have access to this information for")
        raise HttpError(403, gettext("You do not have permission to access this project"))

    if include_pid and not user.is_superuser and user_role_names.isdisjoint(CONSENT_TABLE_PID_ROLES):
        logger.error("Participant identifiers requested by a user who may not see them for project %s", project.name)
        raise HttpError(403, gettext("You do not have permission to view participant identifiers"))

    logger.debug("Getting table data for project %s", project.name)

    query = ParticipantConsent.objects.filter(consent_type__research_project=project)


    if not user.is_superuser and user_role_names.isdisjoint(CONSENT_TABLE_PROJECT_WIDE_ROLES):
        query = query.filter(
            clinic__researchprojectuserrolemap__user=user,
            clinic__researchprojectuserrolemap__project=project,
            clinic__researchprojectuserrolemap__role__name=PROJECT_ROLE_PARTICIPANT_RECRUITER,
        )

    text = DataTableFilter("text")
    date_range = DataTableFilter("date-range")
    columns = [
        DataTableColumn("study_participant__alias1", gettext("Alias"), "string", sortable=True, filter=text),
        DataTableColumn(
            "clinic__clinic_name", gettext("Clinic Name"), "string", sortable=True, filter=text),
        DataTableColumn(
            "clinic__clinic_code", gettext("Clinic Code"), "string", sortable=True, filter=text),
        DataTableColumn("status", gettext("Status"), "string", sortable=True, filter=text),
        DataTableColumn(
            "consent_signed_date", gettext("Signed Date"), "date", sortable=True, filter=None,
            default_sort="desc", default_sort_order=1),
        DataTableColumn(
            "consent_revoked_date", gettext("Revoked Date"), "date", sortable=True, filter=None),
        DataTableColumn("last_updated", gettext("Last Updated"), "datetime", sortable=True, filter=None),
        DataTableColumn(
            "participant_information_version", gettext("Version"), "string", sortable=True,
            filter=text),
        DataTableColumn("source", gettext("Source"), "string", sortable=True, filter=text),
    ]

    if include_pid:
        columns = [
            # Encrypted at rest with a random IV: the database can neither order them nor match a substring, so they
            # are not sortable and only filterable by exact match, through the companion deterministic hash field.
            DataTableColumn(
                "study_participant__person_source_value", gettext("Participant ID"), "string",
                filter=DataTableFilter(
                    "text-exact", hash_field="study_participant__person_source_value_hash")),
            DataTableColumn(
                "study_participant__name", gettext("Name"), "string",
                filter=DataTableFilter("text-exact", hash_field="study_participant__name_hash")),
        ] + columns

    definition = DataTableDefinition(columns=tuple(columns))

    return DataTableSource(query.values(*definition.values_fields), definition)


async def _get_consent_history_data(project: ResearchProject) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Helper function to retrieve consent history data by clinic for the given project_id.
    """
    logger.debug("Entering _get_consent_history_data")
    # Get the clinics associated with the project
    consent_counts_by_clinic_date_and_type = (
        ParticipantConsent.objects
        .filter(consent_type__research_project=project)
        .annotate(
            consent_date=F("consent_signed_date__date"),
            consent_label=F("consent_type__label")
        )
        .values(
            "clinic_id",
            "study_participant_id",
            "consent_type_id",
            "consent_label",
            "consent_date"
        )
        .annotate(consent_count=Count("id"))
        .order_by("clinic_id", "study_participant_id", "consent_label", "consent_date")
    )

    consent_revoked_counts_by_clinic_date_and_type = (
        ParticipantConsent.objects
        .filter(consent_type__research_project=project, consent_revoked_date__isnull=False)
        .annotate(
            revoked_date=F("consent_revoked_date__date"),
            consent_label=F("consent_type__label"),
        )
        .values("clinic_id", "study_participant_id", "consent_type_id", "consent_label", "revoked_date")
        .annotate(consent_count=Count("id"))
        .order_by("clinic_id", "study_participant_id", "consent_label", "revoked_date")
    )

    signed_output = [row async for row in consent_counts_by_clinic_date_and_type]
    revoked_output = [row async for row in consent_revoked_counts_by_clinic_date_and_type]

    logger.debug("Signed sum: %s", sum([row["consent_count"] for row in signed_output]))
    logger.debug("Revoked sum: %s", sum([row["consent_count"] for row in revoked_output]))

    return (
        signed_output,
        revoked_output
    )


async def _get_consent_history_plot_data(
        project: ResearchProject, clinics: list[dict[str, str | UUID]]) -> XYChartDataSchema:
    logger.debug("Fetching data for consented participants for plotting")
    days = (
        ParticipantConsent.objects
        .filter(consent_type__research_project=project)
        .annotate(day=F("consent_signed_date__date"))
        .order_by("clinic_id", "day")
        .values("clinic_id", "day")
        .distinct()
    )

    active_participant_count = (
        ParticipantConsent.objects
        .filter(
            consent_type__research_project=project,
            clinic_id=OuterRef("clinic_id"),
            consent_signed_date__date__lte=OuterRef("day"),
        )
        .filter(
            Q(consent_revoked_date__isnull=True) | Q(consent_revoked_date__date__gt=OuterRef("day"))
        )
        .order_by()
        .values("clinic_id")
        .annotate(count=Count("study_participant_id", distinct=True))
        .values("count")
    )

    query = days.annotate(
        active_participant_count=Subquery(active_participant_count, output_field=IntegerField())
    )

    signed_and_not_revoked_count_by_clinic = [row async for row in query]
    event_dates = sorted(set([row["day"] for row in signed_and_not_revoked_count_by_clinic]))

    formatted_data = {
        clinic["clinic_id"]: [
            {
                "clinic_name": clinic["clinic_name"],
                "timestamp": event_date,
                "active_consent_count": sum([
                    row["active_participant_count"]
                    for row in signed_and_not_revoked_count_by_clinic
                    if row["day"] == event_date and row["clinic_id"] == clinic["clinic_id"]
                ]),
            }
            for event_date in event_dates
        ]
        for clinic in clinics
    }

    clinic_data_items: list[dict[str, Any]] = [
        dict(
            name=(clinic_name := events[0]["clinic_name"] if events else gettext("Unknown Clinic")),
            x=[str(el["timestamp"]) for el in events],
            y=(y_values := list(accumulate(
                [el["active_consent_count"] for el in events],
                lambda previous, current: current if current != 0 else previous
            ))),
            hovertemplate=[f"{clinic_name}: {y_val} (%{{x}})" for y_val in y_values],
        )
        for clinic_id, events in formatted_data.items()
        if clinic_id is not None
    ]

    plot_series = XYChartDataSchema(
        series=[
            XYSeriesSchema(
                name=clinic_data["name"],
                x=clinic_data["x"],
                y=(
                    clinic_data["y"]
                    if ind == 0 else
                    [sum(y) for y in zip(*([clinic_data_items[i]["y"] for i in range(ind)] + [clinic_data["y"]]))]
                ),
                size=None,
                fill="tonexty" if ind > 0 else "tozeroy",
                stackgroup=None,
                hovertemplate=clinic_data["hovertemplate"],
            )
            for ind, clinic_data in enumerate(clinic_data_items)
        ]
    )

    return plot_series

def _format_signed_retracted_data(
        signed_data: list[dict[str, Any]],
        retracted_data: list[dict[str, Any]],
        clinics: list[dict[str, str | Any]]
) -> dict[str, list[dict[str, int]]]:
    """
    Format the signed and retracted data into a dictionary with clinic_id as keys and
    nested dictionaries containing consent_date/retracted_date as keys and consent_count as values.
    """
    signed_data = {
        key: list(group) for key, group in groupby(signed_data, key=itemgetter("clinic_id"))
    }
    signed_data = {
        key: {el["consent_date"]: el.get("consent_count", None) for el in group}
        for key, group in signed_data.items()
    }

    retracted_data = {
        key: list(group) for key, group in groupby(retracted_data, key=itemgetter("clinic_id"))
    }
    retracted_data = {
        key: {el["revoked_date"]: el.get("consent_count", None) for el in group}
        for key, group in retracted_data.items()
    }

    date_times_per_clinic = {
        clinic["clinic_id"]: sorted(set(
            list(
                signed_data.get(clinic["clinic_id"], {}).keys()
            ) + list(
                retracted_data.get(clinic["clinic_id"], {}).keys()
            )
        ))
        for clinic in clinics
    }

    formatted_data = {
        clinic: [
            {
                "timestamp": event_date,
                "consent_count": signed_data.get(clinic, {}).get(event_date, 0),
                "retracted_count": retracted_data.get(clinic, {}).get(event_date, 0)
            }
            for event_date in event_dates
        ]
        for clinic, event_dates in date_times_per_clinic.items()
    }

    return formatted_data

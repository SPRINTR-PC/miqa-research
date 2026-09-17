import logging
from itertools import accumulate, chain, groupby
from operator import itemgetter
from typing import Any

from django.db.models import Count, F
from django.utils.translation import gettext

from MiqaResearch.data.models import ParticipantConsent, ResearchProject
from MiqaResearch.data.serializers.charts.bar import BarChartResponseSchema, BarChartConfigSchema, BarChartDataSchema, \
    BarSeriesSchema
from MiqaResearch.data.serializers.charts.base import ChartGroupingLabelsSchema, ChartGroupingSchema
from MiqaResearch.data.serializers.charts.xy import (
    FilledAreaChartResponseSchema,
    LineChartResponseSchema,
    XYChartDataSchema,
    XYSeriesSchema,
)
from MiqaResearch.data.serializers.participant_consent import (
    ClinicConsentHistorySchema,
    ConsentHistoryEventSchema,
    ProjectConsentHistoryByClinicSchema,
)
from MiqaResearch.readers.research_project_reader import (
    get_project_connected_clinics,
    get_user_project_connected_clinics,
)

logger = logging.getLogger("mires")


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


async def get_consent_history_plot_by_clinic(project: ResearchProject, filled_stacked_chart: bool = True) -> LineChartResponseSchema | FilledAreaChartResponseSchema:
    """
    Get consent count history plot data by clinic for a given project.
    """
    participant_consents_signed, participant_consents_revoked = await _get_consent_history_data(project)

    connected_clinics = await get_project_connected_clinics(project.id)

    formatted_data = _format_consent_data_for_plotting(
        signed_data=participant_consents_signed,
        retracted_data=participant_consents_revoked,
        clinics=connected_clinics,
        filled_stacked_chart=filled_stacked_chart
    )

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
                    legend_title=gettext("Clinic")
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


async def _get_consent_history_data(project: ResearchProject) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Helper function to retrieve consent history data by clinic for the given project_id.
    """
    print("Entering _get_consent_history_data")
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
            "consent_type_id",
            "consent_label",
            "consent_date"
        )
        .annotate(consent_count=Count("id"))
        .order_by("clinic_id", "consent_label", "consent_date")
    )

    consent_revoked_counts_by_clinic_date_and_type = (
        ParticipantConsent.objects
        .filter(consent_type__research_project=project, consent_revoked_date__isnull=False)
        .annotate(
            revoked_date=F("consent_revoked_date__date"),
            consent_label=F("consent_type__label"),
        )
        .values("clinic_id", "consent_type_id", "consent_label", "revoked_date")
        .annotate(consent_count=Count("id"))
        .order_by("clinic_id", "consent_label", "revoked_date")
    )

    print("Before signed query")
    signed_output = [row async for row in consent_counts_by_clinic_date_and_type]
    print("After signed query")
    print("Before revoked query")
    revoked_output = [row async for row in consent_revoked_counts_by_clinic_date_and_type]
    print("After revoked query")

    return (
        signed_output,
        revoked_output
    )

def _format_signed_retracted_data(
        signed_data: list[dict[str, Any]],
        retracted_data: list[dict[str, Any]],
        clinics: list[dict[str, str | Any]],
        for_stacked_plot: bool = False
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

    if for_stacked_plot:
        event_dates = sorted(set(list(chain.from_iterable([
            (
                list(signed_data.get(clinic["clinic_id"], {}).keys())
                + list(retracted_data.get(clinic["clinic_id"], {}).keys())
            )
            for clinic in clinics
        ]))))

        formatted_data = {
            clinic["clinic_id"]: [
                {
                    "timestamp": event_date,
                    "consent_count": signed_data.get(clinic["clinic_id"], {}).get(event_date, 0),
                    "retracted_count": retracted_data.get(clinic["clinic_id"], {}).get(event_date, 0),
                }
                for event_date in event_dates
            ]
            for clinic in clinics
        }
    else:
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


def _format_consent_data_for_plotting(
    signed_data: list[dict[str, Any]],
    retracted_data: list[dict[str, Any]],
    clinics: list[dict[str, str | Any]],
    filled_stacked_chart: bool = True
) -> XYChartDataSchema:
    formatted_data = _format_signed_retracted_data(signed_data, retracted_data, clinics, for_stacked_plot=True)

    clinic_map = {
        clinic["clinic_id"]: clinic["clinic_name"]
        for clinic in clinics
    }

    logger.debug("Formatting XYChartDataSchema based on formatted_data")
    clinic_data_items = [
        dict(
            name=(clinic_name := clinic_map.get(clinic_id, gettext("Unknown Clinic"))),
            x=[el_time.strftime("%Y-%m-%d %H:%M:%S") if (el_time := el.get("timestamp")) else "" for el in data],
            y=(
                y_values := list(
                    accumulate([el.get("consent_count", 0) - el.get("retracted_count", 0) for el in data])
                )
            ),
            hovertemplate=[f"{clinic_name}: {y_val} (%{{x}})" for y_val in y_values],
        )
        for clinic_id, data in formatted_data.items()
        if clinic_id is not None
    ]

    plot_series = XYChartDataSchema(
        series=[
            XYSeriesSchema(
                name=clinic_data["name"],
                x=clinic_data["x"],
                y=(
                    clinic_data["y"]
                    if (ind == 0 or not filled_stacked_chart)
                    else [
                        sum(y)
                        for y in zip(*(
                            [clinic_data_items[i]["y"] for i in range(ind)] + [clinic_data["y"]]))]
                ),
                size=None,
                fill=None if not filled_stacked_chart else ("tonexty"),
                stackgroup=None,
                hovertemplate=clinic_data["hovertemplate"],
            )
            for ind, clinic_data in enumerate(clinic_data_items)
        ]
    )
    logger.debug("Formatted consent history plot series for project")

    return plot_series

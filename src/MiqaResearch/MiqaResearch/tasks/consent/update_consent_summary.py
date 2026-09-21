from django.db import connection, transaction
from django.tasks import task
from django.utils import timezone

from contract.constants.celery import QUEUE_CALCULATE_CONSENT_STATISTICS
from MiqaResearch.data.models import ConsentDailyActiveSummary, ParticipantConsent, ParticipantConsentType

# UTC calendar day of a timestamp column, per backend.
_DAY_SQL = {
    "postgresql": "CAST({col} AT TIME ZONE 'UTC' AS date)",
    "sqlite": "date({col})",
}

_REBUILD_SQL = """
INSERT INTO {summary} (research_project_id, clinic_id, day, active_participant_count, created_at, updated_at)
WITH raw AS (
    SELECT c.clinic_id, c.study_participant_id AS pid, {signed_day} AS day, 1 AS state
    FROM {consent} c JOIN {ctype} t ON t.id = c.consent_type_id
    WHERE t.research_project_id = %(project)s
    UNION ALL
    SELECT c.clinic_id, c.study_participant_id, {revoked_day}, 0
    FROM {consent} c JOIN {ctype} t ON t.id = c.consent_type_id
    WHERE t.research_project_id = %(project)s AND c.consent_revoked_date IS NOT NULL
),
events AS (
    SELECT clinic_id, pid, day, MIN(state) AS state FROM raw GROUP BY clinic_id, pid, day
),
deltas AS (
    SELECT clinic_id, day,
           state - COALESCE(LAG(state) OVER (PARTITION BY clinic_id, pid ORDER BY day), 0) AS delta
    FROM events
),
per_day AS (
    SELECT clinic_id, day, SUM(delta) AS delta FROM deltas GROUP BY clinic_id, day
)
SELECT %(project)s, clinic_id, day,
       SUM(delta) OVER (PARTITION BY clinic_id ORDER BY day), %(now)s, %(now)s
FROM per_day
"""


@task(queue_name=QUEUE_CALCULATE_CONSENT_STATISTICS)
def rebuild_consent_daily_active_summary(project_id: str) -> None:
    _run_query_and_update_summary(project_id)


def _run_query_and_update_summary(project_id: str) -> None:
    day_sql = _DAY_SQL[connection.vendor]
    sql = _REBUILD_SQL.format(
        summary=ConsentDailyActiveSummary._meta.db_table,
        consent=ParticipantConsent._meta.db_table,
        ctype=ParticipantConsentType._meta.db_table,
        signed_day=day_sql.format(col="c.consent_signed_date"),
        revoked_day=day_sql.format(col="c.consent_revoked_date"),
    )
    with transaction.atomic():
        ConsentDailyActiveSummary.objects.filter(research_project_id=project_id)._raw_delete(using="default")
        with connection.cursor() as cursor:
            cursor.execute(sql, {"project": project_id, "now": timezone.now()})

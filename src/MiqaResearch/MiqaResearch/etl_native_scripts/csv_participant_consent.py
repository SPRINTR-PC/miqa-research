"""Native ETL Script: CSV -> participant_consent (#226).

Reads every *.csv file in the input directory. Each CSV row is one participant's consent form:
fixed columns (who, when, where) plus one column per consent type, whose cell says whether that
consent was given. Every given consent becomes one participant_consent row.

Defaults match the SamtyckenUmu export; any of them can be overridden in the Binding's config:

    {
      "delimiter": ",",
      "encoding": "utf-8-sig",
      "timezone": "Europe/Stockholm",
      "consented_values": ["Ja"],
      "source": null,
      "columns": {
        "person_source_value": "Personnummer",
        "name": "Namn",
        "status": "Status",
        "signed": "Signerat",
        "revoked": "Återtaget",
        "clinic": "klinik",
        "participant_information_version": "participant_information_version",
        "ignore": ["Senast Uppdaterad", "Kommentar"]
      }
    }

Every column that isn't one of the above (or listed under "ignore") is a consent type, named by
its header. Dates are "YYYY-MM-DD HH:MM[:SS]" local times in "timezone". Dashes are removed from
person_source_value. Self-contained on purpose: stdlib only, no MiqaResearch imports.
"""
import csv
from datetime import datetime
from zoneinfo import ZoneInfo

DEFAULT_COLUMNS = {
    "person_source_value": "Personnummer",
    "name": "Namn",
    "status": "Status",
    "signed": "Signerat",
    "revoked": "Återtaget",
    "clinic": "klinik",
    "participant_information_version": "participant_information_version",
    "ignore": ["Senast Uppdaterad", "Kommentar"],
}
REQUIRED_COLUMNS = ("person_source_value", "signed", "clinic")
DATETIME_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M")


def main(ctx):
    config = ctx.config
    columns = DEFAULT_COLUMNS | config.get("columns", {})
    timezone = ZoneInfo(config.get("timezone", "Europe/Stockholm"))
    consented_values = set(config.get("consented_values", ["Ja"]))
    source = config.get("source")

    fixed_columns = {columns[key] for key in DEFAULT_COLUMNS if key != "ignore"} | set(columns["ignore"])

    for path in sorted(ctx.input_dir.glob("*.csv")):
        with path.open(newline="", encoding=config.get("encoding", "utf-8-sig")) as csv_file:
            reader = csv.DictReader(csv_file, delimiter=config.get("delimiter", ","))
            missing = [columns[key] for key in REQUIRED_COLUMNS if columns[key] not in (reader.fieldnames or [])]
            if missing:
                raise ValueError(f"{path.name} is missing required column(s): {', '.join(missing)}")
            consent_columns = [header for header in reader.fieldnames if header not in fixed_columns]
            for record in reader:
                for consent_column in consent_columns:
                    if (record[consent_column] or "").strip() not in consented_values:
                        continue
                    yield {
                        "person_source_value": record[columns["person_source_value"]].replace("-", "").strip(),
                        "name": _optional(record, columns["name"]),
                        "consent_type": consent_column.replace('""', '"'),
                        "consent_signed_date": _local_datetime(record[columns["signed"]], timezone),
                        "status": _optional(record, columns["status"]),
                        "consent_revoked_date": _optional_datetime(record, columns["revoked"], timezone),
                        "clinic_code": record[columns["clinic"]].strip(),
                        "participant_information_version": _optional(
                            record, columns["participant_information_version"]),
                        "source": source,
                    }


def _optional(record, column):
    value = (record.get(column) or "").strip()
    return value or None


def _optional_datetime(record, column, timezone):
    value = _optional(record, column)
    return _local_datetime(value, timezone) if value else None


def _local_datetime(value, timezone):
    for datetime_format in DATETIME_FORMATS:
        try:
            return datetime.strptime(value.strip(), datetime_format).replace(tzinfo=timezone).isoformat()
        except ValueError:
            continue
    raise ValueError(f"Unrecognised date {value!r}; expected YYYY-MM-DD HH:MM[:SS].")

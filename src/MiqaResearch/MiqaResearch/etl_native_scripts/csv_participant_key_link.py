"""Native ETL Script: CSV -> participant_key_link (#421).

Reads every *.csv file in the input directory: one row maps one Participant Key (e.g. the pseudonym an
image carries as PatientID) to a Study Participant, given by `alias1` or by `person_source_value`
(exactly one per row). Defaults, all overridable in the Binding's config:

    {
      "key_type": "dicom:PatientID",
      "delimiter": ",",
      "encoding": "utf-8-sig",
      "columns": {"key_value": "key_value", "alias1": "alias1", "person_source_value": "person_source_value"}
    }

A column that is absent from the file is simply not used (so a file may carry only alias1 or only
person_source_value), but the key column must exist. Dashes are removed from person_source_value.
`fill_demographics` is read by the loader, not by this script. Errors name the CSV row, never a value:
the Job log must not carry key values or identities. Self-contained: stdlib only.
"""
import csv

DEFAULT_COLUMNS = {"key_value": "key_value", "alias1": "alias1", "person_source_value": "person_source_value"}


def main(ctx):
    config = ctx.config
    columns = DEFAULT_COLUMNS | config.get("columns", {})
    key_type = config.get("key_type", "dicom:PatientID")

    for path in sorted(ctx.input_dir.glob("*.csv")):
        with path.open(newline="", encoding=config.get("encoding", "utf-8-sig")) as csv_file:
            reader = csv.DictReader(csv_file, delimiter=config.get("delimiter", ","))
            if columns["key_value"] not in (reader.fieldnames or []):
                raise ValueError(f"{path.name} is missing the key column {columns['key_value']!r}")
            for record in reader:
                key_value = (record.get(columns["key_value"]) or "").strip()
                alias1 = (record.get(columns["alias1"]) or "").strip()
                person_source_value = (record.get(columns["person_source_value"]) or "").replace("-", "").strip()
                if not key_value or bool(alias1) == bool(person_source_value):
                    raise ValueError(
                        f"{path.name} row {reader.line_num}: needs a key and exactly one of alias1 or "
                        "person_source_value")
                row = {"key_type": key_type, "key_value": key_value}
                row["alias1" if alias1 else "person_source_value"] = alias1 or person_source_value
                yield row

"""
PROTOTYPE — throwaway view for wayfinder ticket #150 (ETL management UI).
Not wired to real data/models (EtlScript/EtlScriptVersion/PipelineBinding/EtlJob don't exist in
the codebase yet — map #140 is decisions-only). Lives only on branch prototype/etl-management-ui.

Three structurally different answers to "where does ETL management live and how is it organised":
  A — a third tab on the existing per-project dashboard, with sub-tabs (mirrors Consent Statistics).
  B — a dedicated per-project workspace page with a left section sidebar (mirrors Administration).
  C — a single binding-centric hub: cards you expand in place, wizard-first empty state.
"""
from django.shortcuts import render

PROJECT = {"name": "PROTECT-RT", "participant_count": 142, "site_count": 3}

DATATYPES = [
    {"key": "measurement", "label": "Measurement"},
    {"key": "visit_occurrence", "label": "Visit Occurrence"},
]

NATIVE_SCRIPTS = [
    {
        "id": "scr-redcap-labs",
        "name": "REDCap Labs CSV",
        "origin": "native",
        "language": "Python",
        "datatype": "Measurement",
        "description": "Parses a REDCap lab-results export into Measurement rows keyed by participant reference.",
        "current_version": "v3",
        "versions": [
            {"version": "v3", "date": "2026-09-10", "note": "Add unit normalisation for mmol/L vs mg/dL"},
            {"version": "v2", "date": "2026-07-02", "note": "Reject rows with an ambiguous participant match"},
            {"version": "v1", "date": "2026-05-14", "note": "Initial version"},
        ],
        "used_by": 1,
    },
    {
        "id": "scr-visit-log",
        "name": "Visit Log CSV",
        "origin": "native",
        "language": "Python",
        "datatype": "Visit Occurrence",
        "description": "Parses a clinic visit-log export into Visit Occurrence rows.",
        "current_version": "v2",
        "versions": [
            {"version": "v2", "date": "2026-08-21", "note": "Support folder-grouped multi-file exports"},
            {"version": "v1", "date": "2026-06-03", "note": "Initial version"},
        ],
        "used_by": 1,
    },
]

CUSTOM_SCRIPTS = [
    {
        "id": "scr-sitex-lab",
        "name": "Site X Lab Export",
        "origin": "custom",
        "language": "R",
        "datatype": "Measurement",
        "description": "Site X ships a nonstandard lab export; this reshapes it to the Measurement schema.",
        "current_version": "v2",
        "versions": [
            {"version": "v2", "date": "2026-09-18", "note": "Fix decimal comma parsing", "author": "M. Lindqvist"},
            {"version": "v1", "date": "2026-08-30", "note": "Initial version", "author": "M. Lindqvist"},
        ],
        "used_by": 1,
    },
]

ALL_SCRIPTS = NATIVE_SCRIPTS + CUSTOM_SCRIPTS

JOB_1049 = {
    "id": "job-1049",
    "binding": "REDCap Labs CSV → Measurement",
    "status": "succeeded",
    "started": "2026-09-22 09:14",
    "duration": "8s",
    "input": "labs_2026-09-22.csv",
    "checksum": "9f2a1c…e04b",
    "rows": 214,
}
JOB_1039 = {
    "id": "job-1039",
    "binding": "REDCap Labs CSV → Measurement",
    "status": "queued",
    "started": "—",
    "duration": "—",
    "input": "labs_2026-09-21_late.csv",
    "checksum": "—",
    "rows": None,
}
JOB_1048 = {
    "id": "job-1048",
    "binding": "Visit Log CSV → Visit Occurrence",
    "status": "running",
    "started": "2026-09-22 09:41",
    "duration": "—",
    "input": "visits_folder/ (3 files)",
    "checksum": "—",
    "rows": None,
}
JOB_1043 = {
    "id": "job-1043",
    "binding": "Site X Lab Export → Measurement",
    "status": "failed",
    "started": "2026-09-22 07:02",
    "duration": "3s",
    "input": "sx_labs_09-22.csv",
    "checksum": "6b7d90…21fa",
    "rows": 0,
    "exit_code": 2,
    "error": "Participant reference \"P-0442\" is ambiguous (2 matches). All-or-nothing: job failed, no rows loaded.",
    "log_tail": [
        "[00:00] reading /input/sx_labs_09-22.csv",
        "[00:01] shim: loaded R runtime, sourcing main()",
        "[00:02] row 187: participant_reference lookup failed — ambiguous",
        "[00:03] exit 2: validation error, rolled back",
    ],
}

JOBS = [JOB_1049, JOB_1048, JOB_1043, JOB_1039]
FAILED_JOB = JOB_1043

BINDINGS = [
    {
        "id": "bnd-1",
        "datatype": "Measurement",
        "source_bucket": "raw-intake/site-a/labs/",
        "script": "REDCap Labs CSV",
        "script_version": "v3",
        "script_origin": "native",
        "grouping": "Per file",
        "raw_bucket": "etl-raw/measurement/",
        "status": "active",
        "last_job_status": "succeeded",
        "last_job_when": "12 min ago",
        "jobs": [JOB_1049, JOB_1039],
        "versions": NATIVE_SCRIPTS[0]["versions"],
    },
    {
        "id": "bnd-2",
        "datatype": "Visit Occurrence",
        "source_bucket": "raw-intake/site-a/visits/",
        "script": "Visit Log CSV",
        "script_version": "v2",
        "script_origin": "native",
        "grouping": "Per folder (quiescence wait)",
        "raw_bucket": "etl-raw/visit_occurrence/",
        "status": "active",
        "last_job_status": "running",
        "last_job_when": "started 40 sec ago",
        "jobs": [JOB_1048],
        "versions": NATIVE_SCRIPTS[1]["versions"],
    },
    {
        "id": "bnd-3",
        "datatype": "Measurement",
        "source_bucket": "raw-intake/site-x/labs/",
        "script": "Site X Lab Export",
        "script_version": "v2",
        "script_origin": "custom",
        "grouping": "Per file",
        "raw_bucket": "etl-raw/measurement/",
        "status": "needs attention",
        "last_job_status": "failed",
        "last_job_when": "2 hours ago",
        "jobs": [JOB_1043],
        "versions": CUSTOM_SCRIPTS[0]["versions"],
    },
]

VARIANT_ORDER = ["A", "B", "C"]
VARIANT_LABELS = {
    "A": "Project tab, sub-tabs (mirrors Consent Statistics)",
    "B": "Dedicated workspace, section sidebar (mirrors Administration)",
    "C": "Binding-centric hub, expandable cards, wizard-first",
}
SECTIONS = ["bindings", "scripts", "jobs", "defaults"]


def index(request):
    variant = request.GET.get("variant", "A").upper()
    if variant not in VARIANT_ORDER:
        variant = "A"
    section = request.GET.get("section", "bindings")
    if section not in SECTIONS:
        section = "bindings"

    idx = VARIANT_ORDER.index(variant)
    prev_variant = VARIANT_ORDER[idx - 1]
    next_variant = VARIANT_ORDER[(idx + 1) % len(VARIANT_ORDER)]

    context = {
        "variant": variant,
        "variant_label": VARIANT_LABELS[variant],
        "prev_variant": prev_variant,
        "next_variant": next_variant,
        "section": section,
        "project": PROJECT,
        "datatypes": DATATYPES,
        "native_scripts": NATIVE_SCRIPTS,
        "custom_scripts": CUSTOM_SCRIPTS,
        "all_scripts": ALL_SCRIPTS,
        "bindings": BINDINGS,
        "jobs": JOBS,
        "failed_job": FAILED_JOB,
    }
    return render(request, "prototype_etl_management/index.html", context)

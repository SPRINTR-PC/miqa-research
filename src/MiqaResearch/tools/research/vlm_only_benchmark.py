"""Standalone benchmark script for issue #61: VLM-Only Mode against the real
fixture set.

Forces VLM-Only Mode's settled shape (per #60's charting decisions) WITHOUT
touching the shipped pipeline modules:
  - field_matching runs in full (unchanged) -- page localization + text_value
    fallback for non-mark fields.
  - mark_detection is skipped entirely (an empty dict stands in for its
    results -- moot once escalation is forced for every field).
  - vlm_fallback.should_escalate (and merge.should_escalate, a separate name
    bound at import time in merge.py) are monkeypatched to always return
    True so every matched field on every page is escalated.
  - merge.merge_results runs unchanged -- VLM wins where it produced a
    value, classic text_value is the fallback for non-mark fields, "failed"
    otherwise. Same merge.py behavior as Hybrid Mode, unchanged.

Preserved (not merged into main) per #61's resolution -- reusable by #62 to
re-measure once a real OCR Pipeline Mode / GPU Acceleration setting exists,
without needing that plumbing built first.

Run from anywhere via `uv run python tools/research/vlm_only_benchmark.py
...` from the src/MiqaResearch app dir (needs Django settings configured --
see main() for django.setup()). Requires the dev DB (Postgres via
docker-compose or sqlite fallback per settings.py) and a running local
Ollama with qwen3-vl:8b-instruct-q8_0 pulled.

Usage:
    uv run python tools/research/vlm_only_benchmark.py --num-gpu -1 --label gpu-run
    uv run python tools/research/vlm_only_benchmark.py --samples sample_01 --num-gpu 0 --label cpu-run

Note: Ollama does not reload a model's GPU/CPU layer placement on a
per-request `options.num_gpu` change if the model is already warm from a
prior request with a different setting -- run `ollama stop <model>` between
invocations that switch --num-gpu, or you will silently get the previous
run's hardware placement (verify with `ollama ps`'s PROCESSOR column).

Writes a JSON report per invocation to --out (default: report_<label>.json)
and cleans up the PromData rows it creates after each sample (mirrors issue
#50/PR #58's own manual-run cleanup precedent) unless --keep-rows is passed.
Media files always use a TemporaryDirectory MEDIA_ROOT, never real storage.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

# This file lives at tools/research/vlm_only_benchmark.py, two levels below
# the Django app dir (src/MiqaResearch, which contains manage.py) -- default
# --app-dir accordingly; override at call time if the file is moved/copied.
APP_DIR = Path(__file__).resolve().parent.parent.parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-dir", default=str(APP_DIR), help="Path to src/MiqaResearch (contains manage.py)")
    parser.add_argument("--samples", default="", help="Comma-separated sample_* ids; empty = all under fixtures dir")
    parser.add_argument("--fixtures-dir", default=None)
    parser.add_argument(
        "--num-gpu", type=int, default=0, help="Ollama num_gpu option: 0 = CPU-only, -1 = all GPU layers"
    )
    parser.add_argument("--label", default="run")
    parser.add_argument("--out", default=None)
    parser.add_argument("--keep-rows", action="store_true", help="Don't delete the PromData rows created")
    parser.add_argument("--page-timeout", type=float, default=1800.0, help="Per-VLM-call timeout, seconds")
    parser.add_argument(
        "--form-timeout",
        type=float,
        default=14400.0,
        help="Total VLM budget per form, seconds (generous for research runs)",
    )
    args = parser.parse_args()

    app_dir = Path(args.app_dir).resolve()
    sys.path.insert(0, str(app_dir))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "MiqaResearch.settings")

    import django

    django.setup()

    from django.contrib.auth import get_user_model
    from django.core.files import File
    from django.core.management import call_command
    from django.test.utils import override_settings
    from kpforms.helpers import get_form_by_template_id_and_version

    from MiqaResearch.data.management.commands.evaluate_prom_ocr import (
        DEFAULT_TEMPLATE_NAME,
        normalize_value,
        score_sample,
    )
    from MiqaResearch.data.models import PromData, PromFormTemplate, ResearchProject
    from MiqaResearch.tasks.ocr import field_matching, merge, preprocessing, validation, vlm_fallback

    User = get_user_model()

    fixtures_dir = (
        Path(args.fixtures_dir)
        if args.fixtures_dir
        else (app_dir / "tests" / "example_data" / "prom_data" / "prom_samples")
    )
    sample_ids = [s.strip() for s in args.samples.split(",") if s.strip()] or sorted(
        p.name for p in fixtures_dir.iterdir() if p.is_dir() and p.name.startswith("sample_")
    )

    call_command("import_prom_form_template")
    template = PromFormTemplate.objects.get(name=DEFAULT_TEMPLATE_NAME)
    project, _ = ResearchProject.objects.get_or_create(
        name="VLM-Only benchmark (#61)",
        defaults={"description": "Synthetic project for the #61 VLM-Only Mode benchmark script. Safe to delete."},
    )
    user, _ = User.objects.get_or_create(
        username="vlm-only-benchmark-61", defaults={"email": "vlm-only-benchmark-61@example.com"}
    )

    reports = []
    created_prom_data_ids = []

    # Force every field to escalate, everywhere should_escalate is consulted
    # (vlm_fallback's own internal calls, and merge.py's separately-imported
    # name) -- without editing the shipped modules. Media files go to a
    # TemporaryDirectory (same pattern as evaluate_prom_ocr.py) so this never
    # touches real MEDIA_ROOT storage regardless of --keep-rows.
    with (
        mock.patch.object(vlm_fallback, "should_escalate", return_value=True),
        mock.patch.object(merge, "should_escalate", return_value=True),
        override_settings(
            OCR_VLM_PAGE_TIMEOUT_SECONDS=args.page_timeout, OCR_VLM_FORM_TIMEOUT_SECONDS=args.form_timeout
        ),
        TemporaryDirectory(prefix="benchmark_vlm_only_") as tmp_media_root,
        override_settings(MEDIA_ROOT=tmp_media_root),
    ):
        for sample_id in sample_ids:
            sample_dir = fixtures_dir / sample_id
            manifest = json.loads((sample_dir / "manifest.json").read_text(encoding="utf-8"))
            ground_truth = json.loads((sample_dir / "ground_truth.json").read_text(encoding="utf-8"))
            page_count = manifest.get("page_count") or 1

            with (sample_dir / "scan.pdf").open("rb") as scan_file:
                prom_data = PromData.objects.create(
                    project=project,
                    prom_form_template=template,
                    prom_form_file=File(scan_file, name=f"{sample_id}_{args.label}.pdf"),
                    uploaded_by=user,
                )
            created_prom_data_ids.append(prom_data.id)

            report = run_vlm_only_pipeline(
                prom_data,
                sample_id=sample_id,
                page_count=page_count,
                ground_truth=ground_truth,
                num_gpu=args.num_gpu,
                modules=(field_matching, preprocessing, validation, vlm_fallback, merge),
                get_form_by_template_id_and_version=get_form_by_template_id_and_version,
                score_sample=score_sample,
                normalize_value=normalize_value,
            )
            reports.append(report)
            print(json.dumps(report), flush=True)

        out_path = Path(args.out) if args.out else app_dir / f"report_{args.label}.json"
        out_path.write_text(json.dumps({"label": args.label, "num_gpu": args.num_gpu, "reports": reports}, indent=2))
        print(f"Wrote {out_path}")

        # DB rows (PromData) live outside the temp media dir -- clean up
        # explicitly, same as PR #58's own manual-run precedent, unless
        # --keep-rows was passed for debugging. The file field itself is
        # already gone once tmp_media_root is removed on context exit.
        if not args.keep_rows:
            PromData.objects.filter(id__in=created_prom_data_ids).delete()
            print(f"Cleaned up {len(created_prom_data_ids)} PromData rows")


def run_vlm_only_pipeline(
    prom_data,
    *,
    sample_id,
    page_count,
    ground_truth,
    num_gpu,
    modules,
    get_form_by_template_id_and_version,
    score_sample,
    normalize_value,
):
    """Reimplements pipeline.run_pipeline for VLM-Only Mode: same stage
    sequence and timing shape as the shipped pipeline (so stage_seconds stay
    comparable to evaluate_prom_ocr's report), but mark_detection is skipped
    and vlm_fallback._call_ollama's num_gpu option is overridden per-run.
    """
    field_matching, preprocessing, validation, vlm_fallback, merge = modules
    stage_seconds = {}
    page_seconds = []  # per-page VLM latency, for the latency table

    def timed(name, fn, *args):
        start = time.perf_counter()
        result = fn(*args)
        stage_seconds[name] = time.perf_counter() - start
        return result

    template_schema = timed(
        "get_template_schema", get_form_by_template_id_and_version, prom_data.prom_form_template.template_id
    )
    pages = timed("preprocessing", preprocessing.load_pages, prom_data)
    matches = timed("field_matching", field_matching.match_fields, pages, template_schema)
    mark_results = {}  # VLM-Only Mode: mark_detection skipped entirely (#60 charting)

    # Replace _call_ollama to record per-page latency and apply the requested
    # num_gpu override, without touching vlm_fallback.py itself (the shipped
    # module hardcodes num_gpu: 0).
    def patched_call_ollama(prompt, image_b64, timeout):
        import httpx
        from django.conf import settings

        start = time.monotonic()
        response = httpx.post(
            f"{settings.OLLAMA_URL}/api/generate",
            json={
                "model": settings.OLLAMA_MODEL,
                "prompt": prompt,
                "images": [image_b64],
                "stream": False,
                "format": "json",
                "options": {"num_ctx": 16384, "num_gpu": num_gpu},
            },
            timeout=timeout,
        )
        page_seconds.append(time.monotonic() - start)
        response.raise_for_status()
        return json.loads(response.json().get("response", "{}"))

    # should_escalate is already patched to always-True by main()'s outer
    # context manager for the duration of this call.
    with mock.patch.object(vlm_fallback, "_call_ollama", patched_call_ollama):
        vlm_results = timed(
            "vlm_fallback", vlm_fallback.run_vlm_fallback, pages, matches, mark_results, template_schema
        )

    data, extraction_flags = timed("merge", merge.merge_results, matches, mark_results, vlm_results)
    validated_data, fields_out_of_tolerance = timed("validation", validation.validate_submission, data, template_schema)

    correct, total = score_sample(ground_truth["data"], validated_data)
    sources = [flag.get("source") for flag in extraction_flags.values()]

    # Per-field-type breakdown (#17's own report shape) -- lets the resolution
    # comment compare failure modes against #17's original full-list-prompt
    # per-type numbers, not just the overall aggregate.
    field_types = {m.field_id: m.field_type for m in matches}
    predicted_by_field = {entry["fieldId"]: entry["value"] for entry in validated_data}
    by_type: dict[str, dict[str, int]] = {}
    for entry in ground_truth["data"]:
        field_id = entry["fieldId"]
        field_type = field_types.get(field_id, "unknown")
        bucket = by_type.setdefault(field_type, {"correct": 0, "total": 0})
        bucket["total"] += 1
        predicted_value = predicted_by_field.get(field_id)
        if predicted_value is not None and normalize_value(predicted_value) == normalize_value(entry["value"]):
            bucket["correct"] += 1

    return {
        "sample_id": sample_id,
        "page_count": page_count,
        "correct": correct,
        "total": total,
        "accuracy": correct / total if total else 0.0,
        "field_matching_seconds": stage_seconds.get("field_matching", 0.0),
        "vlm_fallback_seconds": stage_seconds.get("vlm_fallback", 0.0),
        "total_seconds": sum(stage_seconds.values()),
        "vlm_calls": len(page_seconds),
        "vlm_call_seconds": page_seconds,
        "mean_vlm_call_seconds": sum(page_seconds) / len(page_seconds) if page_seconds else 0.0,
        "escalated_fields": sources.count("vlm"),
        "classic_fields": sources.count("classic"),
        "failed_fields": sources.count("failed"),
        "by_field_type": by_type,
    }


if __name__ == "__main__":
    main()

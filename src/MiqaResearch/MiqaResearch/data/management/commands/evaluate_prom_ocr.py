import json
import unicodedata
from pathlib import Path
from tempfile import TemporaryDirectory

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files import File
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.test.utils import override_settings

from MiqaResearch.data.management.commands.import_prom_form_template import DEFAULT_TEMPLATE_NAME
from MiqaResearch.data.models import PromData, PromFormTemplate, ResearchProject
from MiqaResearch.tasks.ocr.pipeline import CLASSIC_PATH_STAGES, run_pipeline

User = get_user_model()

# Derived from sample_id, not the top-level manifest.json's scan_path/ground_truth_path
# fields -- those point at a nonexistent tests/fixtures/... location (#17's known bug).
DEFAULT_FIXTURES_DIR = settings.BASE_DIR / "tests" / "example_data" / "prom_data" / "prom_samples"

# docs/prom-ocr-handoff.md §7 acceptance bars.
ACCURACY_BAR = 0.95
CLASSIC_PATH_SECONDS_PER_PAGE_BAR = 2 * 60

EVAL_PROJECT_NAME = "OCR evaluation harness"
EVAL_USER_USERNAME = "ocr-evaluation-harness"


def normalize_value(value):
    """#17's exact scoring normalization: Unicode NFKC + casefold, multi-select as a set."""
    if isinstance(value, list):
        return frozenset(normalize_value(item) for item in value)
    return unicodedata.normalize("NFKC", str(value)).casefold()


def score_sample(ground_truth_entries: list[dict], predicted_entries: list[dict]) -> tuple[int, int]:
    """Returns (correct, total) field counts for one sample, scored against ground truth."""
    predicted_by_field = {entry["fieldId"]: entry["value"] for entry in predicted_entries}
    correct = 0
    for entry in ground_truth_entries:
        predicted_value = predicted_by_field.get(entry["fieldId"])
        if predicted_value is not None and normalize_value(predicted_value) == normalize_value(entry["value"]):
            correct += 1
    return correct, len(ground_truth_entries)


class Command(BaseCommand):
    help = (
        "Evaluates the OCR pipeline against the ground-truth fixture set "
        "(docs/prom-ocr-handoff.md §7): per-sample and overall accuracy, "
        "classic-path latency, escalation rate, and extraction_flags provenance."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--fixtures-dir",
            default=str(DEFAULT_FIXTURES_DIR),
            help=f"Directory containing sample_* fixtures (default: {DEFAULT_FIXTURES_DIR}).",
        )

    def handle(self, *args, **options):
        fixtures_dir = Path(options["fixtures_dir"])
        sample_dirs = sorted(p for p in fixtures_dir.iterdir() if p.is_dir() and p.name.startswith("sample_"))
        if not sample_dirs:
            raise CommandError(f"No sample_* fixtures found under {fixtures_dir}")

        call_command("import_prom_form_template")
        template = PromFormTemplate.objects.get(name=DEFAULT_TEMPLATE_NAME)
        project, _ = ResearchProject.objects.get_or_create(
            name=EVAL_PROJECT_NAME,
            defaults={"description": "Synthetic project used by the evaluate_prom_ocr management command."},
        )
        user, _ = User.objects.get_or_create(
            username=EVAL_USER_USERNAME, defaults={"email": "ocr-evaluation-harness@example.com"}
        )

        with TemporaryDirectory(prefix="evaluate_prom_ocr_") as tmp_media_root:
            with override_settings(MEDIA_ROOT=tmp_media_root):
                reports = [self._evaluate_sample(sample_dir, template, project, user) for sample_dir in sample_dirs]

        self._print_report(reports)

        total_correct = sum(r["correct"] for r in reports)
        total_fields = sum(r["total"] for r in reports)
        overall_accuracy = total_correct / total_fields if total_fields else 0.0

        total_classic_seconds = sum(r["classic_path_seconds"] for r in reports)
        total_pages = sum(r["page_count"] for r in reports)
        mean_classic_seconds_per_page = total_classic_seconds / total_pages if total_pages else 0.0

        failures = []
        if overall_accuracy < ACCURACY_BAR:
            failures.append(f"overall accuracy {overall_accuracy:.1%} is below the {ACCURACY_BAR:.0%} bar")
        if mean_classic_seconds_per_page > CLASSIC_PATH_SECONDS_PER_PAGE_BAR:
            failures.append(
                f"mean classic-path latency {mean_classic_seconds_per_page:.1f}s/page exceeds the "
                f"{CLASSIC_PATH_SECONDS_PER_PAGE_BAR}s/page bar"
            )

        if failures:
            raise CommandError("; ".join(failures))

    def _evaluate_sample(self, sample_dir: Path, template, project, user) -> dict:
        sample_id = sample_dir.name
        manifest = json.loads((sample_dir / "manifest.json").read_text(encoding="utf-8"))
        ground_truth = json.loads((sample_dir / "ground_truth.json").read_text(encoding="utf-8"))
        page_count = manifest.get("page_count") or 1

        with (sample_dir / "scan.pdf").open("rb") as scan_file:
            prom_data = PromData.objects.create(
                project=project,
                prom_form_template=template,
                prom_form_file=File(scan_file, name=f"{sample_id}.pdf"),
                uploaded_by=user,
            )

        result = run_pipeline(prom_data)
        correct, total = score_sample(ground_truth["data"], result.data)

        classic_path_seconds = sum(result.stage_seconds.get(stage, 0.0) for stage in CLASSIC_PATH_STAGES)
        total_seconds = sum(result.stage_seconds.values())
        sources = [flag.get("source") for flag in result.extraction_flags.values()]

        return {
            "sample_id": sample_id,
            "page_count": page_count,
            "correct": correct,
            "total": total,
            "classic_path_seconds": classic_path_seconds,
            "total_seconds": total_seconds,
            "escalated_fields": sources.count("vlm"),
            "failed_fields": sources.count("failed"),
        }

    def _print_report(self, reports: list[dict]):
        header = (
            f"{'sample':<12}{'fields':>10}{'accuracy':>10}"
            f"{'classic s/pg':>14}{'total s/pg':>12}{'escalated':>11}{'failed':>8}"
        )
        self.stdout.write(header)
        self.stdout.write("-" * len(header))
        for r in reports:
            accuracy = r["correct"] / r["total"] if r["total"] else 0.0
            self.stdout.write(
                f"{r['sample_id']:<12}"
                f"{r['correct']:>4}/{r['total']:<5}"
                f"{accuracy:>10.1%}"
                f"{r['classic_path_seconds'] / r['page_count']:>14.2f}"
                f"{r['total_seconds'] / r['page_count']:>12.2f}"
                f"{r['escalated_fields']:>11}"
                f"{r['failed_fields']:>8}"
            )

        total_correct = sum(r["correct"] for r in reports)
        total_fields = sum(r["total"] for r in reports)
        total_classic_seconds = sum(r["classic_path_seconds"] for r in reports)
        total_seconds = sum(r["total_seconds"] for r in reports)
        total_pages = sum(r["page_count"] for r in reports)

        self.stdout.write("-" * len(header))
        overall_accuracy = total_correct / total_fields if total_fields else 0.0
        self.stdout.write(
            f"{'overall':<12}"
            f"{total_correct:>4}/{total_fields:<5}"
            f"{overall_accuracy:>10.1%}"
            f"{total_classic_seconds / total_pages:>14.2f}"
            f"{total_seconds / total_pages:>12.2f}"
            f"{sum(r['escalated_fields'] for r in reports):>11}"
            f"{sum(r['failed_fields'] for r in reports):>8}"
        )

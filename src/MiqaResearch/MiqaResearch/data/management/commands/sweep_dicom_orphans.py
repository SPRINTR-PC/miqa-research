from django.core.management.base import BaseCommand

from MiqaResearch.actions.dicom_ingest.orphan_sweep import sweep_orphans


class Command(BaseCommand):
    help = (
        "Sweep orphan DICOM blobs (no DicomFile row). Dry run by default: no deletes, no email, no audit "
        "event. --delete deletes (and emails staff, audits); --force overrides the circuit breaker."
    )

    def add_arguments(self, parser):
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument("--dry-run", action="store_true", help="Report only (default).")
        mode.add_argument("--delete", action="store_true", help="Delete eligible orphans.")
        parser.add_argument("--force", action="store_true", help="Ignore the circuit breaker.")

    def handle(self, *args, **options):
        delete = options["delete"]
        result = sweep_orphans(delete=delete, force=options["force"], notify=delete, record=delete)
        verb = "deleted" if delete else "would delete"
        count = result.deleted if delete else result.deletable
        self.stdout.write(
            f"listed {result.listed}, orphans {result.reportable} ({result.bytes} bytes), "
            f"new {result.new}, pending {result.pending}; {verb} {count}, failed {result.failed}"
            + ("; circuit breaker tripped (use --force)" if result.breaker_tripped else ""))
        for key in result.sample_keys:
            self.stdout.write(f"  {key}")

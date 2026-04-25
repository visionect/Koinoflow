from django.core.management.base import BaseCommand

from apps.processes.discovery import index_process_version
from apps.processes.enums import StatusChoices
from apps.processes.models import Process


class Command(BaseCommand):
    help = "Backfill or refresh semantic discovery embeddings for published processes."

    def add_arguments(self, parser):
        parser.add_argument("--workspace-id", help="Limit reindexing to a workspace UUID")
        parser.add_argument("--limit", type=int, help="Maximum number of processes to index")
        parser.add_argument("--force", action="store_true", help="Re-embed even if hashes match")

    def handle(self, *args, **options):
        qs = (
            Process.objects.filter(
                status=StatusChoices.PUBLISHED,
                current_version__isnull=False,
            )
            .select_related("department__team", "current_version")
            .order_by("updated_at")
        )
        if options["workspace_id"]:
            qs = qs.filter(department__team__workspace_id=options["workspace_id"])
        if options["limit"]:
            qs = qs[: options["limit"]]

        indexed = 0
        skipped = 0
        for process in qs:
            result = index_process_version(str(process.current_version_id), force=options["force"])
            if result:
                indexed += 1
            else:
                skipped += 1

        self.stdout.write(
            self.style.SUCCESS(f"Indexed {indexed} process embeddings; skipped {skipped}.")
        )

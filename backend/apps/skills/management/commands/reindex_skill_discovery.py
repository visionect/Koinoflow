from django.core.management.base import BaseCommand

from apps.skills.discovery import index_skill_version
from apps.skills.enums import StatusChoices
from apps.skills.models import Skill


class Command(BaseCommand):
    help = "Backfill or refresh semantic discovery embeddings for published skills."

    def add_arguments(self, parser):
        parser.add_argument("--workspace-id", help="Limit reindexing to a workspace UUID")
        parser.add_argument("--limit", type=int, help="Maximum number of skills to index")
        parser.add_argument("--force", action="store_true", help="Re-embed even if hashes match")

    def handle(self, *args, **options):
        qs = (
            Skill.objects.filter(
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
        for skill in qs:
            result = index_skill_version(str(skill.current_version_id), force=options["force"])
            if result:
                indexed += 1
            else:
                skipped += 1

        self.stdout.write(
            self.style.SUCCESS(f"Indexed {indexed} skill embeddings; skipped {skipped}.")
        )

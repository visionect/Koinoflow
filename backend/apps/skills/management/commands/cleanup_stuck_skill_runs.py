from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.skills.models import SkillExecutionRun


class Command(BaseCommand):
    help = (
        "Mark skill execution runs that have been QUEUED or RUNNING for longer "
        "than a threshold as FAILED so they stop blocking the per-skill "
        "concurrency limit."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--queued-older-than-minutes",
            type=int,
            default=15,
            help=(
                "Mark runs whose status is QUEUED and that were created more "
                "than this many minutes ago. Defaults to 15."
            ),
        )
        parser.add_argument(
            "--running-older-than-minutes",
            type=int,
            default=60,
            help=(
                "Mark runs whose status is RUNNING and that were started more "
                "than this many minutes ago. Defaults to 60."
            ),
        )
        parser.add_argument(
            "--workspace-id",
            help="Limit cleanup to a single workspace UUID.",
        )
        parser.add_argument(
            "--skill-slug",
            help="Limit cleanup to a single skill slug.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would change without writing to the database.",
        )

    def handle(self, *args, **options):
        now = timezone.now()
        queued_cutoff = now - timedelta(minutes=options["queued_older_than_minutes"])
        running_cutoff = now - timedelta(minutes=options["running_older_than_minutes"])

        queued = SkillExecutionRun.objects.filter(
            status=SkillExecutionRun.StatusChoices.QUEUED,
            created_at__lt=queued_cutoff,
        )
        running = SkillExecutionRun.objects.filter(
            status=SkillExecutionRun.StatusChoices.RUNNING,
            started_at__lt=running_cutoff,
        )

        if options["workspace_id"]:
            queued = queued.filter(workspace_id=options["workspace_id"])
            running = running.filter(workspace_id=options["workspace_id"])

        if options["skill_slug"]:
            queued = queued.filter(skill__slug=options["skill_slug"])
            running = running.filter(skill__slug=options["skill_slug"])

        queued_count = queued.count()
        running_count = running.count()

        if options["dry_run"]:
            self.stdout.write(
                self.style.WARNING(
                    f"[dry-run] Would mark {queued_count} QUEUED and "
                    f"{running_count} RUNNING runs as FAILED."
                )
            )
            for run in queued.values("id", "skill__slug", "created_at")[:50]:
                self.stdout.write(
                    f"  QUEUED  {run['id']}  "
                    f"skill={run['skill__slug']}  "
                    f"created={run['created_at']}"
                )
            for run in running.values("id", "skill__slug", "started_at")[:50]:
                self.stdout.write(
                    f"  RUNNING {run['id']}  "
                    f"skill={run['skill__slug']}  "
                    f"started={run['started_at']}"
                )
            return

        queued_updated = queued.update(
            status=SkillExecutionRun.StatusChoices.FAILED,
            error_message=(
                "Run was stuck in QUEUED and never dispatched. Cleared by cleanup_stuck_skill_runs."
            ),
            started_at=now,
            finished_at=now,
            updated_at=now,
        )
        running_updated = running.update(
            status=SkillExecutionRun.StatusChoices.FAILED,
            error_message=(
                "Run was stuck in RUNNING past its expected window. "
                "Cleared by cleanup_stuck_skill_runs."
            ),
            finished_at=now,
            updated_at=now,
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Marked {queued_updated} QUEUED and {running_updated} RUNNING runs as FAILED."
            )
        )

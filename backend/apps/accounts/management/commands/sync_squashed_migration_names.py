from django.core.management.base import BaseCommand
from django.db import connection

_RENAMES: list[tuple[str, str, str]] = [
    ("billing", "0001_squashed_0003_alter_plan_tier", "0001_initial"),
    ("orgs", "0001_squashed_0002_featureflag_workspacefeatureflag", "0001_initial"),
    ("processes", "0001_squashed_0002_versionfile", "0001_initial"),
    ("usage", "0001_squashed_0005_alter_usageevent_client_type", "0001_initial"),
]


class Command(BaseCommand):
    help = (
        "Update django_migrations after squashed files were renamed to 0001_initial. "
        "Run once per database before migrate."
    )

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            for app, old_name, new_name in _RENAMES:
                cursor.execute(
                    "UPDATE django_migrations SET name = %s WHERE app = %s AND name = %s",
                    [new_name, app, old_name],
                )
                if cursor.rowcount:
                    self.stdout.write(
                        self.style.SUCCESS(f"Renamed {app}.{old_name} -> {app}.{new_name}")
                    )

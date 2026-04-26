from django.core.management.base import BaseCommand
from django.db import connection

_RENAMES: list[tuple[str, str, str]] = [
    ("billing", "0001_squashed_0003_alter_plan_tier", "0001_initial"),
    ("orgs", "0001_squashed_0002_featureflag_workspacefeatureflag", "0001_initial"),
    ("processes", "0001_squashed_0002_versionfile", "0001_initial"),
    ("usage", "0001_squashed_0005_alter_usageevent_client_type", "0001_initial"),
]


def _table_exists(cursor, table_name: str) -> bool:
    cursor.execute("SELECT to_regclass(%s)", [table_name])
    return cursor.fetchone()[0] is not None


def _column_exists(cursor, table_name: str, column_name: str) -> bool:
    cursor.execute(
        """
        SELECT 1
          FROM information_schema.columns
         WHERE table_schema = current_schema()
           AND table_name = %s
           AND column_name = %s
        """,
        [table_name, column_name],
    )
    return cursor.fetchone() is not None


def _migration_exists(cursor, app: str, name: str) -> bool:
    cursor.execute(
        "SELECT 1 FROM django_migrations WHERE app = %s AND name = %s",
        [app, name],
    )
    return cursor.fetchone() is not None


def _record_migration(cursor, app: str, name: str) -> bool:
    if _migration_exists(cursor, app, name):
        return False
    cursor.execute(
        "INSERT INTO django_migrations (app, name, applied) VALUES (%s, %s, NOW())",
        [app, name],
    )
    return True


def _rename_table(cursor, old_name: str, new_name: str) -> bool:
    if not _table_exists(cursor, old_name) or _table_exists(cursor, new_name):
        return False
    cursor.execute(f'ALTER TABLE "{old_name}" RENAME TO "{new_name}"')
    return True


def _rename_column(cursor, table_name: str, old_name: str, new_name: str) -> bool:
    if not _table_exists(cursor, table_name):
        return False
    if not _column_exists(cursor, table_name, old_name) or _column_exists(
        cursor, table_name, new_name
    ):
        return False
    cursor.execute(f'ALTER TABLE "{table_name}" RENAME COLUMN "{old_name}" TO "{new_name}"')
    return True


def _rename_constraint(cursor, table_name: str, old_name: str, new_name: str) -> bool:
    if not _table_exists(cursor, table_name):
        return False
    cursor.execute(
        """
        SELECT 1
          FROM pg_constraint c
          JOIN pg_class t ON t.oid = c.conrelid
          JOIN pg_namespace n ON n.oid = t.relnamespace
         WHERE n.nspname = current_schema()
           AND t.relname = %s
           AND c.conname = %s
        """,
        [table_name, old_name],
    )
    if cursor.fetchone() is None:
        return False
    cursor.execute(
        """
        SELECT 1
          FROM pg_constraint c
          JOIN pg_class t ON t.oid = c.conrelid
          JOIN pg_namespace n ON n.oid = t.relnamespace
         WHERE n.nspname = current_schema()
           AND t.relname = %s
           AND c.conname = %s
        """,
        [table_name, new_name],
    )
    if cursor.fetchone() is not None:
        return False
    cursor.execute(f'ALTER TABLE "{table_name}" RENAME CONSTRAINT "{old_name}" TO "{new_name}"')
    return True


def _rename_index(cursor, old_name: str, new_name: str) -> bool:
    cursor.execute("SELECT to_regclass(%s)", [old_name])
    if cursor.fetchone()[0] is None:
        return False
    cursor.execute("SELECT to_regclass(%s)", [new_name])
    if cursor.fetchone()[0] is not None:
        return False
    cursor.execute(f'ALTER INDEX "{old_name}" RENAME TO "{new_name}"')
    return True


class Command(BaseCommand):
    help = (
        "Update django_migrations after squashed/app-renamed migrations changed names. "
        "Run once per database before migrate."
    )

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            if not _table_exists(cursor, "django_migrations"):
                self.stdout.write("No django_migrations table yet; nothing to sync.")
                return

            for app, old_name, new_name in _RENAMES:
                cursor.execute(
                    "UPDATE django_migrations SET name = %s WHERE app = %s AND name = %s",
                    [new_name, app, old_name],
                )
                if cursor.rowcount:
                    self.stdout.write(
                        self.style.SUCCESS(f"Renamed {app}.{old_name} -> {app}.{new_name}")
                    )

            self._sync_processes_to_skills(cursor)

    def _sync_processes_to_skills(self, cursor):
        if not _migration_exists(cursor, "processes", "0001_initial"):
            return

        changed: list[str] = []

        # The process->skill rename removed the old app label, so this command
        # performs the already-applied production schema rename before Django
        # checks the current migration graph. Everything is guarded so fresh
        # databases and partially retried jobs are no-ops.
        for old_name, new_name in [
            ("process_audit_rule", "skill_audit_rule"),
            ("process", "skill"),
            ("process_version", "skill_version"),
            ("process_shared_with", "skill_shared_with"),
            ("process_discovery_embedding", "skill_discovery_embedding"),
        ]:
            if _rename_table(cursor, old_name, new_name):
                changed.append(f"table {old_name} -> {new_name}")

        for table_name, old_name, new_name in [
            ("core_settings", "process_audit_id", "skill_audit_id"),
            ("core_settings", "allow_agent_process_updates", "allow_agent_skill_updates"),
            ("staleness_alert_rule", "notify_process_owner", "notify_skill_owner"),
            ("skill_version", "process_id", "skill_id"),
            ("skill_shared_with", "process_id", "skill_id"),
        ]:
            if _rename_column(cursor, table_name, old_name, new_name):
                changed.append(f"column {table_name}.{old_name} -> {new_name}")

        for table_name, old_name, new_name in [
            ("skill", "uq_process_dept_slug", "uq_skill_dept_slug"),
            ("skill_version", "uq_version_process_number", "uq_version_skill_number"),
        ]:
            if _rename_constraint(cursor, table_name, old_name, new_name):
                changed.append(f"constraint {old_name} -> {new_name}")

        for old_name, new_name in [
            ("idx_process_dept_status", "idx_skill_dept_status"),
            ("idx_process_status_updated", "idx_skill_status_updated"),
            ("idx_process_slug", "idx_skill_slug"),
            ("idx_process_updated_at", "idx_skill_updated_at"),
            ("idx_process_search_trgm", "idx_skill_search_trgm"),
            ("idx_process_visibility", "idx_skill_visibility"),
            ("idx_proc_disc_model_dims", "idx_skill_disc_model_dims"),
            ("idx_proc_disc_hash", "idx_skill_disc_hash"),
            ("idx_proc_disc_hnsw", "idx_skill_disc_hnsw"),
        ]:
            if _rename_index(cursor, old_name, new_name):
                changed.append(f"index {old_name} -> {new_name}")

        for app, name in [
            ("orgs", "0004_rename_process_to_skill"),
            ("skills", "0000_create_vector_extension"),
            ("skills", "0001_initial"),
        ]:
            if _record_migration(cursor, app, name):
                changed.append(f"recorded {app}.{name}")

        for entry in changed:
            self.stdout.write(self.style.SUCCESS(f"Synced process->skill: {entry}"))

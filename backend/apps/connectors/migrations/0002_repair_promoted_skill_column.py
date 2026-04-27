from django.db import migrations


def add_promoted_skill_column_if_missing(apps, schema_editor):
    table_name = "capture_candidate"
    column_name = "promoted_skill_id"
    with schema_editor.connection.cursor() as cursor:
        columns = schema_editor.connection.introspection.get_table_description(cursor, table_name)
    if any(column.name == column_name for column in columns):
        return

    CaptureCandidate = apps.get_model("connectors", "CaptureCandidate")
    promoted_skill = CaptureCandidate._meta.get_field("promoted_skill")
    schema_editor.add_field(CaptureCandidate, promoted_skill)


class Migration(migrations.Migration):
    dependencies = [
        ("connectors", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(add_promoted_skill_column_if_missing, migrations.RunPython.noop),
    ]

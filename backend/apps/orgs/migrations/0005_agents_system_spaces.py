from django.db import migrations, models


AGENTS_SYSTEM_KIND = "agents"


def _unique_slug(CoreSlug, entity_type, base, **scope):
    candidate = base
    suffix = 2
    while CoreSlug.objects.filter(entity_type=entity_type, slug=candidate, **scope).exists():
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def create_agents_spaces(apps, schema_editor):
    Workspace = apps.get_model("orgs", "Workspace")
    Team = apps.get_model("orgs", "Team")
    Department = apps.get_model("orgs", "Department")
    CoreSlug = apps.get_model("orgs", "CoreSlug")

    for workspace in Workspace.objects.all():
        team = Team.objects.filter(workspace=workspace, system_kind=AGENTS_SYSTEM_KIND).first()
        if team is None:
            team = Team.objects.create(
                workspace=workspace,
                name="Agents",
                system_kind=AGENTS_SYSTEM_KIND,
            )
        if not CoreSlug.objects.filter(entity_type="team", entity_id=team.id).exists():
            CoreSlug.objects.create(
                entity_type="team",
                entity_id=team.id,
                slug=_unique_slug(
                    CoreSlug,
                    "team",
                    "agents",
                    scope_workspace=workspace,
                ),
                scope_workspace=workspace,
            )

        department = Department.objects.filter(
            team=team,
            system_kind=AGENTS_SYSTEM_KIND,
        ).first()
        if department is None:
            department = Department.objects.create(
                team=team,
                name="Agents",
                system_kind=AGENTS_SYSTEM_KIND,
            )
        if not CoreSlug.objects.filter(entity_type="department", entity_id=department.id).exists():
            CoreSlug.objects.create(
                entity_type="department",
                entity_id=department.id,
                slug=_unique_slug(
                    CoreSlug,
                    "department",
                    "agents",
                    scope_team=team,
                ),
                scope_team=team,
            )


class Migration(migrations.Migration):
    dependencies = [
        ("orgs", "0004_rename_process_to_skill"),
    ]

    operations = [
        migrations.AddField(
            model_name="team",
            name="system_kind",
            field=models.CharField(blank=True, db_index=True, default="", max_length=50),
        ),
        migrations.AddField(
            model_name="department",
            name="system_kind",
            field=models.CharField(blank=True, db_index=True, default="", max_length=50),
        ),
        migrations.RunPython(create_agents_spaces, migrations.RunPython.noop),
    ]

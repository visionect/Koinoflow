from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("orgs", "0003_coresettings_allow_agent_process_updates"),
    ]

    operations = [
        # Rename notify_process_owner on StalenessAlertRule
        migrations.RenameField(
            model_name="stalenessalertrule",
            old_name="notify_process_owner",
            new_name="notify_skill_owner",
        ),
        # Rename model and table
        migrations.RenameModel(
            old_name="ProcessAuditRule",
            new_name="SkillAuditRule",
        ),
        migrations.AlterModelTable(
            name="skillauditrule",
            table="skill_audit_rule",
        ),
        # Rename FK on CoreSettings
        migrations.RenameField(
            model_name="coresettings",
            old_name="process_audit",
            new_name="skill_audit",
        ),
        # Rename boolean on CoreSettings
        migrations.RenameField(
            model_name="coresettings",
            old_name="allow_agent_process_updates",
            new_name="allow_agent_skill_updates",
        ),
    ]

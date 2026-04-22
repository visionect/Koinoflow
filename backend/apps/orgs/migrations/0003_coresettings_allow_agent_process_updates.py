from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orgs', '0002_stalenessalertrule_coresettings_staleness_alert'),
    ]

    operations = [
        migrations.AddField(
            model_name='coresettings',
            name='allow_agent_process_updates',
            field=models.BooleanField(default=None, null=True),
        ),
    ]

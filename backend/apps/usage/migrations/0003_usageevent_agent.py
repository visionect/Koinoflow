import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("agents", "0001_initial"),
        ("usage", "0002_remove_usageevent_usage_event_process_fff70b_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="usageevent",
            name="agent",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="usage_events",
                to="agents.agent",
            ),
        ),
    ]

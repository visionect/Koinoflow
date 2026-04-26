from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("orgs", "0005_agents_system_spaces"),
    ]

    operations = [
        migrations.AlterField(
            model_name="team",
            name="system_kind",
            field=models.CharField(blank=True, db_index=True, default="", max_length=50),
        ),
        migrations.AlterField(
            model_name="department",
            name="system_kind",
            field=models.CharField(blank=True, db_index=True, default="", max_length=50),
        ),
    ]

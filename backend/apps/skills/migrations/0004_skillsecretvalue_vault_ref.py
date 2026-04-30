from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("skills", "0003_skill_execution_secrets"),
    ]

    operations = [
        migrations.AddField(
            model_name="skillsecretvalue",
            name="vault_ref",
            field=models.CharField(blank=True, default="", max_length=512),
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orgs", "0007_onboarding"),
    ]

    operations = [
        migrations.AddField(
            model_name="coresettings",
            name="sandbox_min_role",
            field=models.CharField(
                blank=True,
                default=None,
                max_length=20,
                null=True,
            ),
        ),
    ]

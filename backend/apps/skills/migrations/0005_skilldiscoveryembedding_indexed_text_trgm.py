import django.contrib.postgres.indexes
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("skills", "0004_skillsecretvalue_vault_ref"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="skilldiscoveryembedding",
            index=django.contrib.postgres.indexes.GinIndex(
                fields=["indexed_text"],
                name="idx_skill_disc_trgm",
                opclasses=["gin_trgm_ops"],
            ),
        ),
    ]

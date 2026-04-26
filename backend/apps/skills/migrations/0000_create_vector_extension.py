from django.db import migrations


class Migration(migrations.Migration):
    """Ensure the pgvector and pg_trgm extensions exist before creating tables."""

    initial = True

    dependencies = []

    operations = [
        migrations.RunSQL(
            sql="CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS pg_trgm;",
            reverse_sql="SELECT 1;",
        ),
    ]

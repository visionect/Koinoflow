import uuid

import django.db.models.deletion
import pgvector.django
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("processes", "0006_versionfile_binary_content"),
    ]

    operations = [
        pgvector.django.VectorExtension(),
        migrations.CreateModel(
            name="ProcessDiscoveryEmbedding",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("embedding", pgvector.django.VectorField(dimensions=768)),
                ("embedding_model", models.CharField(max_length=100)),
                ("embedding_dimensions", models.PositiveSmallIntegerField(default=768)),
                ("content_hash", models.CharField(max_length=64)),
                ("indexed_text", models.TextField()),
                ("indexed_at", models.DateTimeField()),
                (
                    "version",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="discovery_embedding",
                        to="processes.processversion",
                    ),
                ),
            ],
            options={
                "db_table": "process_discovery_embedding",
            },
        ),
        migrations.AddIndex(
            model_name="processdiscoveryembedding",
            index=models.Index(
                fields=["embedding_model", "embedding_dimensions"],
                name="idx_proc_disc_model_dims",
            ),
        ),
        migrations.AddIndex(
            model_name="processdiscoveryembedding",
            index=models.Index(fields=["content_hash"], name="idx_proc_disc_hash"),
        ),
        migrations.AddIndex(
            model_name="processdiscoveryembedding",
            index=pgvector.django.HnswIndex(
                fields=["embedding"],
                m=16,
                ef_construction=64,
                name="idx_proc_disc_hnsw",
                opclasses=["vector_cosine_ops"],
            ),
        ),
    ]

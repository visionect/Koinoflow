import hashlib

from django.db import migrations, models


def forwards(apps, schema_editor):
    VersionFile = apps.get_model("processes", "VersionFile")
    for vf in VersionFile.objects.all().iterator():
        raw = (vf.content or "").encode("utf-8")
        vf.content_bytes = raw
        vf.mime_type = "text/plain"
        vf.encoding = "utf-8"
        vf.sha256 = hashlib.sha256(raw).hexdigest() if raw else ""
        vf.size_bytes = len(raw)
        vf.save(
            update_fields=[
                "content_bytes",
                "mime_type",
                "encoding",
                "sha256",
                "size_bytes",
            ]
        )


class Migration(migrations.Migration):
    dependencies = [
        ("processes", "0005_processversion_reverted_from"),
    ]

    operations = [
        migrations.AddField(
            model_name="versionfile",
            name="content_bytes",
            field=models.BinaryField(blank=True, default=b""),
        ),
        migrations.AddField(
            model_name="versionfile",
            name="mime_type",
            field=models.CharField(blank=True, default="text/plain", max_length=100),
        ),
        migrations.AddField(
            model_name="versionfile",
            name="encoding",
            field=models.CharField(blank=True, default="utf-8", max_length=20),
        ),
        migrations.AddField(
            model_name="versionfile",
            name="sha256",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AlterField(
            model_name="versionfile",
            name="file_type",
            field=models.CharField(
                choices=[
                    ("python", "Python"),
                    ("markdown", "Markdown"),
                    ("html", "Html"),
                    ("yaml", "Yaml"),
                    ("json", "Json"),
                    ("javascript", "Javascript"),
                    ("typescript", "Typescript"),
                    ("shell", "Shell"),
                    ("image", "Image"),
                    ("pdf", "Pdf"),
                    ("binary", "Binary"),
                    ("text", "Text"),
                    ("other", "Other"),
                ],
                default="text",
                max_length=50,
            ),
        ),
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]

# Generated manually — adds VersionFile model for support files (CoW)

import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('processes', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='VersionFile',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('path', models.CharField(max_length=500)),
                ('content', models.TextField(default='')),
                ('file_type', models.CharField(choices=[('python', 'Python'), ('markdown', 'Markdown'), ('html', 'Html'), ('yaml', 'Yaml'), ('javascript', 'Javascript'), ('typescript', 'Typescript'), ('shell', 'Shell'), ('text', 'Text'), ('other', 'Other')], default='text', max_length=50)),
                ('size_bytes', models.PositiveIntegerField(default=0)),
                ('is_deleted', models.BooleanField(default=False)),
                ('version', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='files', to='processes.processversion')),
            ],
            options={
                'db_table': 'version_file',
                'indexes': [models.Index(fields=['version', 'path'], name='idx_vfile_version_path')],
                'constraints': [models.UniqueConstraint(fields=('version', 'path'), name='uq_version_file_path')],
            },
        ),
    ]

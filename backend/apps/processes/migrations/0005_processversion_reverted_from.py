from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('processes', '0004_processversion_koinoflow_metadata'),
    ]

    operations = [
        migrations.AddField(
            model_name='processversion',
            name='reverted_from',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='revert_children',
                to='processes.processversion',
            ),
        ),
    ]

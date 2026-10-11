from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('slideshow', '0031_mosque_sync_failures'),
    ]

    operations = [
        migrations.AddField(
            model_name='mosque',
            name='sync_failing_since',
            field=models.DateTimeField(
                blank=True, null=True,
                help_text='When the current run of consecutive sync failures began; '
                          'null when the last sync succeeded.',
            ),
        ),
    ]

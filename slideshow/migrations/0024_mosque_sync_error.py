from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('slideshow', '0023_alter_mosque_lat_long'),
    ]

    operations = [
        migrations.AddField(
            model_name='mosque',
            name='sync_error',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Last website-sync failure message; empty when the last sync succeeded.',
                max_length=255,
            ),
        ),
    ]

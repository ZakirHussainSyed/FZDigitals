from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('slideshow', '0024_mosque_sync_error'),
    ]

    operations = [
        migrations.AddField(
            model_name='prayertime',
            name='jummah2',
            field=models.TimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='prayertime',
            name='jummah3',
            field=models.TimeField(blank=True, null=True),
        ),
    ]

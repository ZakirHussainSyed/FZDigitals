from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('slideshow', '0025_prayertime_jummah2_jummah3'),
    ]

    operations = [
        migrations.AddField(
            model_name='mosque',
            name='jummah_section',
            field=models.CharField(
                blank=True,
                help_text="Keyword locating this mosque's Jumu'ah section on a shared multi-location website (e.g. 'North' or '21 St'); blank = first Jumu'ah section",
                max_length=100,
            ),
        ),
    ]

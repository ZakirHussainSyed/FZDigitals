from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('slideshow', '0026_mosque_jummah_section'),
    ]

    operations = [
        migrations.AddField(
            model_name='prayertime',
            name='maghrib_after_sunset',
            field=models.BooleanField(
                default=False,
                help_text='When on, Maghrib is set to 1 minute after the computed sunset.'),
        ),
    ]

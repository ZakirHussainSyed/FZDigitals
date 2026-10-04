# Generated migration for Device.mosque field

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('slideshow', '0027_prayertime_maghrib_after_sunset'),
    ]

    operations = [
        migrations.AddField(
            model_name='device',
            name='mosque',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='devices',
                to='slideshow.mosque'
            ),
        ),
    ]

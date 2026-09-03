import uuid

from django.db import migrations, models

import slideshow.models


def fill_tokens(apps, schema_editor):
    Device = apps.get_model('slideshow', 'Device')
    for device in Device.objects.all():
        device.token = uuid.uuid4().hex
        device.save(update_fields=['token'])


class Migration(migrations.Migration):

    dependencies = [
        ('slideshow', '0008_auto_20260902_0612'),
    ]

    operations = [
        migrations.AddField(
            model_name='device',
            name='token',
            field=models.CharField(default=slideshow.models.generate_device_token, max_length=64),
        ),
        migrations.RunPython(fill_tokens, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='device',
            name='token',
            field=models.CharField(default=slideshow.models.generate_device_token, max_length=64, unique=True),
        ),
    ]

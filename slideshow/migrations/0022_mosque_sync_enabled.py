from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('slideshow', '0021_mosque_website_prayer_sync'),
    ]

    operations = [
        migrations.AddField(
            model_name='mosque',
            name='sync_enabled',
            field=models.BooleanField(
                default=False,
                help_text='When on, prayer times come from the website PDF; when off, manual entries are used.',
            ),
        ),
    ]

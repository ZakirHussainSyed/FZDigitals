from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('slideshow', '0020_mediafile_position'),
    ]

    operations = [
        migrations.AddField(
            model_name='mosque',
            name='website_url',
            field=models.URLField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='mosque',
            name='timezone',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
        migrations.AddField(
            model_name='mosque',
            name='prayer_synced_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='prayertime',
            name='source',
            field=models.CharField(
                default='default',
                help_text='default | pdf | manual — sync never overwrites manual rows',
                max_length=10,
            ),
        ),
    ]

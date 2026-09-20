from django.db import migrations, models


def backfill_positions(apps, schema_editor):
    """Preserve the current display order (newest first, Meta.ordering
    -created_at) by numbering each (user, screen) group 0..n in that order."""
    MediaFile = apps.get_model('slideshow', 'MediaFile')
    groups = MediaFile.objects.values_list('user_id', 'screen').distinct()
    for user_id, screen in groups:
        qs = MediaFile.objects.filter(user_id=user_id, screen=screen).order_by('-created_at', '-id')
        for i, f in enumerate(qs):
            if f.position != i:
                f.position = i
                f.save(update_fields=['position'])


class Migration(migrations.Migration):

    dependencies = [
        ('slideshow', '0019_prayer_sunset'),
    ]

    operations = [
        migrations.AddField(
            model_name='mediafile',
            name='position',
            field=models.PositiveIntegerField(
                default=0,
                help_text='Playlist order within (user, screen); lower plays first',
            ),
        ),
        migrations.RunPython(backfill_positions, migrations.RunPython.noop),
    ]

# Generated migration for PrayerTimeOverride + manual-row data migration

from django.db import migrations, models
import django.db.models.deletion


_OVERRIDE_FIELDS = ('fajr', 'dhuhr', 'asr', 'maghrib', 'isha', 'sunset',
                    'jummah', 'jummah2', 'jummah3')


def manual_rows_to_overrides(apps, schema_editor):
    """Move source='manual' PrayerTime values into the override table.

    For website-synced mosques only Jummah carries over — those are often
    absent from site PDFs and the only values admins set by hand; stale
    manual daily times revert to the website (they were the divergence
    bug). For manual-only mosques everything carries over so display is
    unchanged. Either way the base row flips to 'default' so sync can own
    it again (sync skips only source='manual' rows).
    """
    PrayerTime = apps.get_model('slideshow', 'PrayerTime')
    PrayerTimeOverride = apps.get_model('slideshow', 'PrayerTimeOverride')
    for row in PrayerTime.objects.filter(source='manual').select_related('mosque').iterator():
        if row.mosque.sync_enabled and row.mosque.website_url:
            defaults = {f: getattr(row, f) for f in ('jummah', 'jummah2', 'jummah3')}
            defaults['maghrib_after_sunset'] = None
        else:
            defaults = {f: getattr(row, f) for f in _OVERRIDE_FIELDS}
            defaults['maghrib_after_sunset'] = row.maghrib_after_sunset
        if any(v is not None for v in defaults.values()):
            PrayerTimeOverride.objects.update_or_create(
                mosque_id=row.mosque_id, date=row.date, defaults=defaults)
        row.source = 'default'
        row.save(update_fields=['source'])


def overrides_to_manual_rows(apps, schema_editor):
    """Reverse: copy overrides back onto PrayerTime rows marked manual."""
    PrayerTime = apps.get_model('slideshow', 'PrayerTime')
    PrayerTimeOverride = apps.get_model('slideshow', 'PrayerTimeOverride')
    for ov in PrayerTimeOverride.objects.iterator():
        defaults = {f: getattr(ov, f) for f in _OVERRIDE_FIELDS}
        defaults['maghrib_after_sunset'] = bool(ov.maghrib_after_sunset)
        defaults['source'] = 'manual'
        # Non-nullable base fields need real values; skip rows where an
        # override left required fields unset (no data to restore anyway).
        if any(defaults[f] is None for f in ('fajr', 'dhuhr', 'asr',
                                             'maghrib', 'isha')):
            continue
        PrayerTime.objects.update_or_create(
            mosque_id=ov.mosque_id, date=ov.date, defaults=defaults)


class Migration(migrations.Migration):

    dependencies = [
        ('slideshow', '0028_device_mosque'),
    ]

    operations = [
        migrations.CreateModel(
            name='PrayerTimeOverride',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField()),
                ('fajr', models.TimeField(blank=True, null=True)),
                ('dhuhr', models.TimeField(blank=True, null=True)),
                ('asr', models.TimeField(blank=True, null=True)),
                ('maghrib', models.TimeField(blank=True, null=True)),
                ('isha', models.TimeField(blank=True, null=True)),
                ('sunset', models.TimeField(blank=True, null=True)),
                ('jummah', models.TimeField(blank=True, null=True)),
                ('jummah2', models.TimeField(blank=True, null=True)),
                ('jummah3', models.TimeField(blank=True, null=True)),
                ('maghrib_after_sunset', models.BooleanField(blank=True, null=True, help_text='NULL = inherit from synced row; set = override.')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('mosque', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='overrides', to='slideshow.mosque')),
            ],
            options={
                'ordering': ['-date'],
                'unique_together': {('mosque', 'date')},
            },
        ),
        migrations.RunPython(manual_rows_to_overrides, overrides_to_manual_rows),
    ]

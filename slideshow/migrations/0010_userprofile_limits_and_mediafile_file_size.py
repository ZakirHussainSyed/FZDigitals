from django.db import migrations, models


def create_missing_profiles(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    UserProfile = apps.get_model('slideshow', 'UserProfile')
    for user in User.objects.all():
        UserProfile.objects.get_or_create(user=user)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('slideshow', '0009_device_token'),
    ]

    operations = [
        migrations.AddField(
            model_name='mediafile',
            name='file_size',
            field=models.PositiveIntegerField(default=0, help_text='File size in bytes'),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='max_screens_per_slideshow',
            field=models.PositiveIntegerField(default=0, help_text='Max devices per slideshow; 0 = unlimited'),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='max_slideshows',
            field=models.PositiveIntegerField(default=5, help_text='Max number of slideshows this user can create'),
        ),
        migrations.AddField(
            model_name='userprofile',
            name='storage_quota_mb',
            field=models.PositiveIntegerField(default=100, help_text='Total upload quota in MB'),
        ),
        migrations.RunPython(create_missing_profiles, noop),
    ]

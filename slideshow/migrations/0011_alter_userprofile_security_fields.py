from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('slideshow', '0010_userprofile_limits_and_mediafile_file_size'),
    ]

    operations = [
        migrations.AlterField(
            model_name='userprofile',
            name='security_answer',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
        migrations.AlterField(
            model_name='userprofile',
            name='security_question',
            field=models.CharField(blank=True, choices=[('pet', 'What was the name of your first pet?'), ('school', 'What was the name of your first school?'), ('city', 'In which city were you born?'), ('mother', 'What is your mother\'s maiden name?'), ('job', 'What was your first job?')], default='', max_length=50),
        ),
    ]

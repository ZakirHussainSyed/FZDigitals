from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('slideshow', '0022_mosque_sync_enabled'),
    ]

    operations = [
        migrations.AlterField(
            model_name='mosque',
            name='latitude',
            field=models.DecimalField(blank=True, decimal_places=12, max_digits=16, null=True),
        ),
        migrations.AlterField(
            model_name='mosque',
            name='longitude',
            field=models.DecimalField(blank=True, decimal_places=12, max_digits=16, null=True),
        ),
    ]

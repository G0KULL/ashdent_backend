from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('patients', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='patient',
            name='balance_adjustment',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12),
        ),
    ]

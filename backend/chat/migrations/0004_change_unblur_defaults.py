# Migration to alter default values for unblur fields to True
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chat', '0003_matchsession_unblur_price_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='matchsession',
            name='user_a_unblurred',
            field=models.BooleanField(default=True),
        ),
        migrations.AlterField(
            model_name='matchsession',
            name='user_b_unblurred',
            field=models.BooleanField(default=True),
        ),
    ]

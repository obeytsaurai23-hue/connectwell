# Generated migration to add charge_viewers to User
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='charge_viewers',
            field=models.BooleanField(default=False),
        ),
    ]

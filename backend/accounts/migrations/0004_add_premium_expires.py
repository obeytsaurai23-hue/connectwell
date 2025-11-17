from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_user_birth_year_user_gender_user_location'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='premium_expires_at',
            field=models.DateTimeField(null=True, blank=True),
        ),
    ]

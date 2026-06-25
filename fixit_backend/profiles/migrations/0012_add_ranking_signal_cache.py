
from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('profiles', '0011_migrate_json_addresses'),
    ]

    operations = [
        migrations.AddField(
            model_name='providerprofile',
            name='cached_response_speed',
            field=models.FloatField(default=0.5),
        ),
        migrations.AddField(
            model_name='providerprofile',
            name='cached_cancellation_rate',
            field=models.FloatField(default=0.0),
        ),
        migrations.AddField(
            model_name='providerprofile',
            name='cached_repeat_bonus',
            field=models.FloatField(default=0.0),
        ),
        migrations.AddField(
            model_name='providerprofile',
            name='cached_recency_score',
            field=models.FloatField(default=0.1),
        ),
        migrations.AddField(
            model_name='providerprofile',
            name='ranking_signals_updated_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
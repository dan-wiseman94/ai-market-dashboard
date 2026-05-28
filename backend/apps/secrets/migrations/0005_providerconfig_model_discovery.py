from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('secrets_app', '0004_providerconfig_supports_tools'),
    ]

    operations = [
        migrations.AddField(
            model_name='providerconfig',
            name='discovered_models',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='providerconfig',
            name='models_synced_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]

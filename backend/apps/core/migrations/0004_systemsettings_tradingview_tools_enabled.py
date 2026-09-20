from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0003_systemsettings_retention_book_days_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="systemsettings",
            name="tradingview_tools_enabled",
            field=models.BooleanField(blank=True, null=True),
        ),
    ]

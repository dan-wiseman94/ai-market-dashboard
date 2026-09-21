from django.db import migrations, models


class Migration(migrations.Migration):
    """Ten more nullable SystemSettings override columns.

    Schema only, deliberately: NULL means "inherit the Django setting", so the new
    defaults reach existing installs through settings resolution. Writing values here
    would replace that inherit sentinel with a frozen snapshot of today's defaults.
    """

    dependencies = [
        ("core", "0004_systemsettings_tradingview_tools_enabled"),
    ]

    operations = [
        migrations.AddField(
            model_name="systemsettings",
            name="ai_calibration_routing_enabled",
            field=models.BooleanField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="systemsettings",
            name="calibration_drift_sentinel_enabled",
            field=models.BooleanField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="systemsettings",
            name="anomaly_sweep_enabled",
            field=models.BooleanField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="systemsettings",
            name="returns_adjust_dividends",
            field=models.BooleanField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="systemsettings",
            name="ai_investigation_max_iterations",
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="systemsettings",
            name="ai_autonomous_daily_cap_usd",
            field=models.FloatField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="systemsettings",
            name="ai_calibration_routing_min_scored",
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="systemsettings",
            name="ai_calibration_routing_max_age_days",
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="systemsettings",
            name="restore_from_ui_enabled",
            field=models.BooleanField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="systemsettings",
            name="ai_chat_max_tool_iterations",
            field=models.IntegerField(blank=True, null=True),
        ),
    ]

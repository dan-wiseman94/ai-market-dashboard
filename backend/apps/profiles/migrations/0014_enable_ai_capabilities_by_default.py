from __future__ import annotations

from django.db import migrations, models

from apps.profiles.migrations._enable_capabilities import enable_capabilities


class Migration(migrations.Migration):
    dependencies = [
        ("profiles", "0013_backfill_default_includes"),
    ]

    operations = [
        migrations.AlterField(
            model_name="tradingprofile",
            name="enable_tools",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "Expose the default Toolset (get_quote, fetch_ohlc, search_news, "
                    "get_option_chain, compute_indicator) to Claude."
                ),
            ),
        ),
        migrations.AlterField(
            model_name="tradingprofile",
            name="enable_thinking",
            field=models.BooleanField(
                default=True,
                help_text="Turn on extended thinking on Claude.",
            ),
        ),
        migrations.AlterField(
            model_name="tradingprofile",
            name="enable_memory",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "Expose the Memory tool with a per-profile namespace under "
                    "/data/memory/<profile_id>/."
                ),
            ),
        ),
        migrations.AddField(
            model_name="tradingprofile",
            name="effort",
            field=models.CharField(
                choices=[
                    ("low", "Low"),
                    ("medium", "Medium"),
                    ("high", "High"),
                    ("xhigh", "Extra high"),
                    ("max", "Max"),
                ],
                default="high",
                help_text="Reasoning effort applied to this profile's runs.",
                max_length=8,
            ),
        ),
        # A model default reaches new rows only; existing profiles need the write.
        migrations.RunPython(enable_capabilities, migrations.RunPython.noop),
    ]

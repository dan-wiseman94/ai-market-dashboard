"""Absorb AIPrediction from the removed apps.predictions into apps.observer (the
forecasts are promoted from observer fires), preserving the table. State: CreateModel.
Database: a following RunPython that creates predictions_aiprediction only if missing —
fresh DB builds it with Django's DDL; existing DB keeps its table. AIPrediction has no
inbound FK, so apps.predictions left cleanly.
"""

import django.db.models.deletion
from django.db import migrations, models


def _create_table_if_missing(apps, schema_editor):
    if "predictions_aiprediction" in schema_editor.connection.introspection.table_names():
        return
    schema_editor.create_model(apps.get_model("observer", "AIPrediction"))


def _drop_table(apps, schema_editor):
    schema_editor.delete_model(apps.get_model("observer", "AIPrediction"))


class Migration(migrations.Migration):

    dependencies = [
        ("observer", "0014_alter_notification_kind"),
        ("profiles", "0008_seed_macro_fundamentals_preset"),
        ("snapshots", "0013_snapshot_candidate_positions"),
        ("threads", "0009_absorb_userfile"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="AIPrediction",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("ticker", models.CharField(db_index=True, max_length=16)),
                        ("direction", models.CharField(choices=[("bullish", "Bullish"), ("bearish", "Bearish"), ("neutral", "Neutral")], max_length=16)),
                        ("horizon_days", models.PositiveIntegerField()),
                        ("invalidation_price", models.DecimalField(blank=True, decimal_places=4, max_digits=14, null=True)),
                        ("invalidation_note", models.CharField(blank=True, default="", max_length=300)),
                        ("forward_return_pct", models.FloatField(blank=True, null=True)),
                        ("verdict", models.CharField(blank=True, choices=[("correct", "Correct"), ("incorrect", "Incorrect"), ("mixed", "Mixed"), ("inconclusive", "Inconclusive")], default="", max_length=16)),
                        ("confidence", models.FloatField()),
                        ("rationale", models.TextField(blank=True, default="")),
                        ("provider", models.CharField(db_index=True, max_length=32)),
                        ("model", models.CharField(db_index=True, max_length=64)),
                        ("predicted_at", models.DateTimeField(db_index=True)),
                        ("resolve_at", models.DateTimeField(db_index=True)),
                        ("status", models.CharField(choices=[("open", "open"), ("resolving", "resolving"), ("resolved", "resolved"), ("invalidated", "invalidated")], default="open", max_length=12)),
                        ("resolved_at", models.DateTimeField(blank=True, null=True)),
                        ("invalidated_at", models.DateTimeField(blank=True, null=True)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        ("profile", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="profiles.tradingprofile")),
                        ("source_message", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="threads.message")),
                        ("source_snapshot", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="snapshots.snapshot")),
                    ],
                    options={
                        "db_table": "predictions_aiprediction",
                        "indexes": [
                            models.Index(fields=["ticker", "status"], name="predictions_ticker_1d0072_idx"),
                            models.Index(fields=["provider", "model", "status"], name="predictions_provide_889ac6_idx"),
                            models.Index(fields=["status", "resolve_at"], name="predictions_status_452c48_idx"),
                        ],
                    },
                ),
            ],
            database_operations=[],
        ),
        migrations.RunPython(_create_table_if_missing, _drop_table),
    ]

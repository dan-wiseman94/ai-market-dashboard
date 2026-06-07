"""Move Position from the removed apps.portfolio into apps.thesis, preserving the
table. State: CreateModel(thesis.Position, db_table="portfolio_position"). Database:
a following RunPython that creates portfolio_position only if missing — a fresh DB
builds it with Django's DDL; an existing DB keeps its table untouched. The FKs target
profiles.TradingProfile + thesis.Thesis (both guaranteed by the dependencies).
"""

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


def _create_table_if_missing(apps, schema_editor):
    if "portfolio_position" in schema_editor.connection.introspection.table_names():
        return
    schema_editor.create_model(apps.get_model("thesis", "Position"))


def _drop_table(apps, schema_editor):
    schema_editor.delete_model(apps.get_model("thesis", "Position"))


class Migration(migrations.Migration):

    dependencies = [
        ("profiles", "0008_seed_macro_fundamentals_preset"),
        ("thesis", "0007_thesis_invalidation_note"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="Position",
                    fields=[
                        (
                            "id",
                            models.BigAutoField(
                                auto_created=True,
                                primary_key=True,
                                serialize=False,
                                verbose_name="ID",
                            ),
                        ),
                        ("ticker", models.CharField(db_index=True, max_length=16)),
                        (
                            "direction",
                            models.CharField(
                                choices=[("long", "Long"), ("short", "Short")],
                                default="long",
                                max_length=8,
                            ),
                        ),
                        ("quantity", models.DecimalField(decimal_places=4, max_digits=18)),
                        ("avg_cost", models.DecimalField(decimal_places=4, max_digits=14)),
                        ("opened_at", models.DateTimeField(default=django.utils.timezone.now)),
                        ("closed_at", models.DateTimeField(blank=True, null=True)),
                        (
                            "close_price",
                            models.DecimalField(
                                blank=True, decimal_places=4, max_digits=14, null=True
                            ),
                        ),
                        (
                            "realized_pnl",
                            models.DecimalField(
                                blank=True, decimal_places=4, max_digits=18, null=True
                            ),
                        ),
                        (
                            "status",
                            models.CharField(
                                choices=[("open", "Open"), ("closed", "Closed")],
                                db_index=True,
                                default="open",
                                max_length=8,
                            ),
                        ),
                        ("note", models.TextField(blank=True, default="")),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        (
                            "profile",
                            models.ForeignKey(
                                blank=True,
                                null=True,
                                on_delete=django.db.models.deletion.SET_NULL,
                                related_name="positions",
                                to="profiles.tradingprofile",
                            ),
                        ),
                        (
                            "thesis",
                            models.ForeignKey(
                                blank=True,
                                null=True,
                                on_delete=django.db.models.deletion.SET_NULL,
                                related_name="positions",
                                to="thesis.thesis",
                            ),
                        ),
                    ],
                    options={
                        "db_table": "portfolio_position",
                        "ordering": ["-opened_at"],
                        "indexes": [
                            models.Index(
                                fields=["status", "-opened_at"],
                                name="portfolio_p_status_dfaf95_idx",
                            ),
                            models.Index(
                                fields=["ticker", "status"], name="portfolio_p_ticker_10dbfb_idx"
                            ),
                        ],
                    },
                ),
            ],
            database_operations=[],
        ),
        migrations.RunPython(_create_table_if_missing, _drop_table),
    ]

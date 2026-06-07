"""Absorb RegimeReading from the removed apps.regime into apps.strategy, preserving
the table (regime completes the M15 strategist cluster here). State: CreateModel.
Database: a following RunPython that creates regime_regimereading only if missing —
fresh DB builds it with Django's DDL; existing DB keeps its table. RegimeReading is a
leaf (no FKs), so no other app's migration depended on regime — it left cleanly.
"""

from django.db import migrations, models


def _create_table_if_missing(apps, schema_editor):
    if "regime_regimereading" in schema_editor.connection.introspection.table_names():
        return
    schema_editor.create_model(apps.get_model("strategy", "RegimeReading"))


def _drop_table(apps, schema_editor):
    schema_editor.delete_model(apps.get_model("strategy", "RegimeReading"))


class Migration(migrations.Migration):

    dependencies = [
        ("strategy", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="RegimeReading",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                        ("composite", models.CharField(max_length=20)),
                        ("axes", models.JSONField(default=dict)),
                        ("drivers", models.JSONField(default=list)),
                        ("narrative", models.TextField(blank=True, default="")),
                        ("inputs", models.JSONField(default=dict)),
                        ("changed_axes", models.JSONField(default=list)),
                    ],
                    options={"db_table": "regime_regimereading", "ordering": ["-created_at"]},
                ),
            ],
            database_operations=[],
        ),
        migrations.RunPython(_create_table_if_missing, _drop_table),
    ]

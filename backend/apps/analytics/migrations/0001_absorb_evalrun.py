"""Absorb EvalRun from the removed apps.aieval into apps.analytics, preserving the
table. State: CreateModel(analytics.EvalRun, db_table="aieval_evalrun"). Database: a
following RunPython that creates the table only when missing — a fresh DB (CI/new
install) builds it with Django's own DDL; an existing DB (where the old
apps.aieval.0001 created it) keeps its table untouched. apps.aieval is fully removed.
"""

from django.db import migrations, models


def _create_table_if_missing(apps, schema_editor):
    if "aieval_evalrun" in schema_editor.connection.introspection.table_names():
        return
    schema_editor.create_model(apps.get_model("analytics", "EvalRun"))


def _drop_table(apps, schema_editor):
    schema_editor.delete_model(apps.get_model("analytics", "EvalRun"))


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="EvalRun",
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
                        ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                        (
                            "source",
                            models.CharField(
                                choices=[("manual", "Manual"), ("scheduled", "Scheduled")],
                                default="manual",
                                max_length=12,
                            ),
                        ),
                        ("label", models.CharField(default="baseline", max_length=64)),
                        ("model", models.CharField(db_index=True, max_length=128)),
                        ("horizon", models.PositiveIntegerField(blank=True, null=True)),
                        ("n", models.PositiveIntegerField(default=0)),
                        ("skipped", models.PositiveIntegerField(default=0)),
                        ("scored", models.PositiveIntegerField(default=0)),
                        ("hit_rate", models.FloatField(blank=True, null=True)),
                        ("brier", models.FloatField(blank=True, null=True)),
                        ("avg_confidence", models.FloatField(blank=True, null=True)),
                        ("calibration_error", models.FloatField(blank=True, null=True)),
                        ("calibration", models.JSONField(default=list)),
                        ("examples", models.JSONField(default=list)),
                    ],
                    options={
                        "db_table": "aieval_evalrun",
                        "ordering": ["-created_at"],
                        "indexes": [
                            models.Index(
                                fields=["model", "-created_at"],
                                name="aieval_eval_model_27727c_idx",
                            )
                        ],
                    },
                ),
            ],
            database_operations=[],
        ),
        migrations.RunPython(_create_table_if_missing, _drop_table),
    ]

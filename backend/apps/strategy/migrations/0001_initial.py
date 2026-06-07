"""Initial strategy migration — absorbs CoverageNote/CoverageRevision (ex-coverage),
WarRoomRun (ex-warroom), DeskEntry (ex-desk), preserving every table. State: the four
CreateModels. Database: a following RunPython that creates each table only if missing,
in FK order — a fresh DB builds them with Django's DDL; an existing DB keeps its
tables. The cross-app FKs that blocked piecemeal removal (warroom→coverage,
desk→warroom) are now intra-app, so the old apps' migrations leave cleanly.
"""

import django.db.models.deletion
from django.db import migrations, models

# FK order: CoverageNote before CoverageRevision/WarRoomRun (both FK it);
# WarRoomRun before DeskEntry (FKs it).
_MODELS_IN_ORDER = ["CoverageNote", "CoverageRevision", "WarRoomRun", "DeskEntry"]


def _create_tables_if_missing(apps, schema_editor):
    existing = set(schema_editor.connection.introspection.table_names())
    for name in _MODELS_IN_ORDER:
        model = apps.get_model("strategy", name)
        if model._meta.db_table not in existing:
            schema_editor.create_model(model)


def _drop_tables(apps, schema_editor):
    for name in reversed(_MODELS_IN_ORDER):
        schema_editor.delete_model(apps.get_model("strategy", name))


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("book", "0002_booksnapshot_var_beta"),
        ("snapshots", "0013_snapshot_candidate_positions"),
        ("thesis", "0009_lesson"),
        ("threads", "0009_absorb_userfile"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="CoverageNote",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("ticker", models.CharField(max_length=16, unique=True)),
                        ("stance", models.CharField(choices=[("bull", "Bull"), ("bear", "Bear"), ("neutral", "Neutral")], default="neutral", max_length=8)),
                        ("conviction", models.PositiveSmallIntegerField(default=1)),
                        ("bull_case", models.TextField(blank=True, default="")),
                        ("bear_case", models.TextField(blank=True, default="")),
                        ("key_levels", models.JSONField(default=dict)),
                        ("watching_for", models.TextField(blank=True, default="")),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                    ],
                    options={"db_table": "coverage_coveragenote", "ordering": ["ticker"]},
                ),
                migrations.CreateModel(
                    name="CoverageRevision",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("prior", models.JSONField(default=dict)),
                        ("new", models.JSONField(default=dict)),
                        ("reason", models.TextField()),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("note", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="revisions", to="strategy.coveragenote")),
                        ("source_snapshot", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="snapshots.snapshot")),
                    ],
                    options={"db_table": "coverage_coveragerevision", "ordering": ["-created_at"]},
                ),
                migrations.CreateModel(
                    name="WarRoomRun",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                        ("subject_kind", models.CharField(max_length=16)),
                        ("subject_label", models.CharField(blank=True, default="", max_length=200)),
                        ("free_prompt", models.TextField(blank=True, default="")),
                        ("params", models.JSONField(default=dict)),
                        ("verdict", models.JSONField(default=dict)),
                        ("confidence", models.FloatField(blank=True, null=True)),
                        ("status", models.CharField(choices=[("running", "Running"), ("done", "Done"), ("error", "Error")], default="done", max_length=16)),
                        ("error", models.TextField(blank=True, default="")),
                        ("book_snapshot", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="book.booksnapshot")),
                        ("coverage_note", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="strategy.coveragenote")),
                        ("thesis", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="thesis.thesis")),
                        ("thread", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="warroom_runs", to="threads.thread")),
                    ],
                    options={"db_table": "warroom_warroomrun", "ordering": ["-created_at"]},
                ),
                migrations.CreateModel(
                    name="DeskEntry",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                        ("anomaly_type", models.CharField(db_index=True, max_length=32)),
                        ("ticker", models.CharField(blank=True, db_index=True, default="", max_length=16)),
                        ("severity", models.FloatField(default=0.0)),
                        ("evidence", models.JSONField(default=dict)),
                        ("finding", models.TextField(blank=True, default="")),
                        ("suggested_actions", models.JSONField(default=list)),
                        ("status", models.CharField(choices=[("new", "New"), ("acted", "Acted"), ("dismissed", "Dismissed")], db_index=True, default="new", max_length=16)),
                        ("investigation_thread", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="threads.thread")),
                        ("warroom_run", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="strategy.warroomrun")),
                    ],
                    options={
                        "db_table": "desk_deskentry",
                        "ordering": ["-created_at"],
                        "indexes": [models.Index(fields=["ticker", "anomaly_type", "-created_at"], name="desk_desken_ticker_ac168d_idx")],
                    },
                ),
            ],
            database_operations=[],
        ),
        migrations.RunPython(_create_tables_if_missing, _drop_tables),
    ]

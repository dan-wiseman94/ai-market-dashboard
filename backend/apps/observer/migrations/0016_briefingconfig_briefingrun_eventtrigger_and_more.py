"""Absorb EventTrigger/TriggerFiring (ex-triggers) + BriefingConfig/BriefingRun
(ex-briefing) into apps.observer (the automated-monitoring domain), preserving every
table. State: the four CreateModels + their indexes/constraint. Database: a following
RunPython that creates each table only if missing (FK order), then re-seeds the
``triggers.evaluate_triggers`` PeriodicTask that the removed apps.triggers.0003 used to
seed (idempotent — update_or_create, so existing DBs are untouched). Neither app had an
inbound FK, so they left cleanly.
"""

import datetime
import json

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

# FK order: EventTrigger before TriggerFiring (which FKs it); Briefing* are independent.
_MODELS_IN_ORDER = ["BriefingConfig", "BriefingRun", "EventTrigger", "TriggerFiring"]


def _create_tables_if_missing(apps, schema_editor):
    existing = set(schema_editor.connection.introspection.table_names())
    for name in _MODELS_IN_ORDER:
        model = apps.get_model("observer", name)
        if model._meta.db_table not in existing:
            schema_editor.create_model(model)


def _drop_tables(apps, schema_editor):
    for name in reversed(_MODELS_IN_ORDER):
        schema_editor.delete_model(apps.get_model("observer", name))


def _seed_evaluate_triggers(apps, schema_editor):
    """Re-seed the evaluate_triggers PeriodicTask (was apps.triggers.0003). Idempotent."""
    every = getattr(settings, "TRIGGER_TICK_SECONDS", 10)
    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    interval, _ = IntervalSchedule.objects.get_or_create(every=every, period="seconds")
    PeriodicTask.objects.update_or_create(
        name="triggers.evaluate_triggers",
        defaults={
            "task": "triggers.evaluate_triggers",
            "interval": interval,
            "enabled": True,
            "kwargs": json.dumps({}),
        },
    )


def _unseed_evaluate_triggers(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name="triggers.evaluate_triggers").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("observer", "0015_aiprediction"),
        ("profiles", "0008_seed_macro_fundamentals_preset"),
        ("snapshots", "0013_snapshot_candidate_positions"),
        ("thesis", "0009_lesson"),
        ("threads", "0009_absorb_userfile"),
        ("django_celery_beat", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="BriefingConfig",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("enabled", models.BooleanField(default=True)),
                        ("send_at_local", models.TimeField(default=datetime.time(8, 30))),
                        ("news_lookback_hours", models.PositiveIntegerField(default=14)),
                        ("events_within_days", models.PositiveIntegerField(default=7)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        ("profile", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="profiles.tradingprofile")),
                    ],
                    options={"db_table": "briefing_briefingconfig"},
                ),
                migrations.CreateModel(
                    name="BriefingRun",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                        ("status", models.CharField(choices=[("assembling", "Assembling"), ("ready", "Ready"), ("failed", "Failed")], default="assembling", max_length=12)),
                        ("data", models.JSONField(default=dict)),
                        ("scheduled_date", models.DateField(blank=True, null=True, unique=True)),
                        ("error", models.TextField(blank=True, default="")),
                        ("snapshot", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="snapshots.snapshot")),
                        ("synthesis_message", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to="threads.message")),
                    ],
                    options={"db_table": "briefing_briefingrun", "ordering": ["-created_at"]},
                ),
                migrations.CreateModel(
                    name="EventTrigger",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("name", models.CharField(max_length=100)),
                        ("condition", models.JSONField()),
                        ("cooldown_seconds", models.PositiveIntegerField(default=1800)),
                        ("enabled", models.BooleanField(default=True)),
                        ("investigate", models.BooleanField(default=False, help_text="When True, a fire runs a bounded tool-using investigation instead of a single observation.")),
                        ("last_fired_at", models.DateTimeField(blank=True, null=True)),
                        ("created_at", models.DateTimeField(auto_now_add=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        ("profile", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="triggers", to="profiles.tradingprofile")),
                        ("source_thesis", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="guard_triggers", to="thesis.thesis")),
                    ],
                    options={"db_table": "triggers_eventtrigger"},
                ),
                migrations.CreateModel(
                    name="TriggerFiring",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("fired_at", models.DateTimeField(auto_now_add=True)),
                        ("matched_values", models.JSONField()),
                        ("cost_capped", models.BooleanField(default=False)),
                        ("snapshot", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="trigger_firings", to="snapshots.snapshot")),
                        ("thread", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="trigger_firings", to="threads.thread")),
                        ("trigger", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="firings", to="observer.eventtrigger")),
                    ],
                    options={"db_table": "triggers_triggerfiring"},
                ),
                migrations.AddIndex(
                    model_name="eventtrigger",
                    index=models.Index(fields=["enabled", "-last_fired_at"], name="triggers_ev_enabled_3f6a3d_idx"),
                ),
                migrations.AddConstraint(
                    model_name="eventtrigger",
                    constraint=models.UniqueConstraint(fields=("profile", "name"), name="unique_trigger_name_per_profile"),
                ),
                migrations.AddIndex(
                    model_name="triggerfiring",
                    index=models.Index(fields=["trigger", "-fired_at"], name="triggers_tr_trigger_0dabc0_idx"),
                ),
                migrations.AddIndex(
                    model_name="triggerfiring",
                    index=models.Index(fields=["-fired_at"], name="triggers_tr_fired_a_eb8dc2_idx"),
                ),
            ],
            database_operations=[],
        ),
        migrations.RunPython(_create_tables_if_missing, _drop_tables),
        migrations.RunPython(_seed_evaluate_triggers, _unseed_evaluate_triggers),
    ]

"""Investigation mode on by default for observer schedules and event triggers,
plus the briefing's AI-synthesis switch.

A field default reaches new rows only, so the RunPython arms the rows that already
exist. Both autonomous paths stay bounded: AI_INVESTIGATION_MAX_ITERATIONS caps the
tool rounds and AI_AUTONOMOUS_DAILY_CAP_USD is a separate, lower daily ceiling
checked before every autonomous run.
"""

from django.db import migrations, models


def arm_investigate(apps, schema_editor):
    apps.get_model("observer", "ObserverSchedule").objects.filter(investigate=False).update(
        investigate=True
    )
    apps.get_model("observer", "EventTrigger").objects.filter(investigate=False).update(
        investigate=True
    )


def unarm_noop(apps, schema_editor):
    """No-op. The forward pass cannot record which rows were already armed, so
    disarming everything would silently discard a user's deliberate opt-in.
    Reverse the schema; leave the data as the user left it.
    """


class Migration(migrations.Migration):
    dependencies = [
        ("observer", "0021_aiprediction_uniq_open_prediction_per_ticker_horizon_profile"),
    ]

    operations = [
        migrations.AlterField(
            model_name="observerschedule",
            name="investigate",
            field=models.BooleanField(
                default=True,
                help_text="When True (plain mode only), the fire runs a bounded tool-using "
                "investigation instead of a single observation. Bounded by "
                "AI_INVESTIGATION_MAX_ITERATIONS tool rounds and the separate "
                "AI_AUTONOMOUS_DAILY_CAP_USD daily ceiling.",
            ),
        ),
        migrations.AlterField(
            model_name="eventtrigger",
            name="investigate",
            field=models.BooleanField(
                default=True,
                help_text="When True, a fire runs a bounded tool-using investigation "
                "instead of a single observation. Bounded by AI_INVESTIGATION_MAX_ITERATIONS "
                "tool rounds and the separate AI_AUTONOMOUS_DAILY_CAP_USD daily ceiling.",
            ),
        ),
        migrations.AlterField(
            model_name="briefingconfig",
            name="enabled",
            field=models.BooleanField(
                default=True,
                help_text="When True, observer.briefing_run_scheduled assembles and posts one "
                "briefing per local day once send_at_local has passed.",
            ),
        ),
        migrations.AddField(
            model_name="briefingconfig",
            name="synthesis_enabled",
            field=models.BooleanField(
                default=True,
                help_text="When True, a ready briefing also pays for one AI synthesis pass "
                "over the assembled data. When False the deterministic sections still "
                "render; only the AI call is skipped.",
            ),
        ),
        migrations.RunPython(arm_investigate, unarm_noop),
    ]

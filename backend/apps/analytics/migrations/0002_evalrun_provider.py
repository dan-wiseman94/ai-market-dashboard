"""Record which provider served an EvalRun's model.

``AddField`` stamps every existing row 'claude'. That is right for the scheduled
harness (claude-only) but wrong for a manual ``aieval --provider openai`` run, so
``_backfill_provider_from_catalog`` corrects rows whose model id is a catalog entry
of another provider. The reverse is a no-op: the column is dropped, and the
pre-migration rows carried no provider to restore.
"""

from django.db import migrations, models


def _backfill_provider_from_catalog(apps, schema_editor):
    from apps.ai.catalog import list_models

    EvalRun = apps.get_model("analytics", "EvalRun")
    for model_info in list_models():
        if model_info.provider == "claude":
            continue
        EvalRun.objects.filter(model=model_info.id).update(provider=model_info.provider)


class Migration(migrations.Migration):
    dependencies = [
        ("analytics", "0001_absorb_evalrun"),
    ]

    operations = [
        migrations.AddField(
            model_name="evalrun",
            name="provider",
            field=models.CharField(db_index=True, default="claude", max_length=32),
        ),
        migrations.RunPython(_backfill_provider_from_catalog, migrations.RunPython.noop),
    ]

"""Correct the provider stamped on pre-existing EvalRun rows.

``0002`` added the column with ``default="claude"``, which is right for the
scheduled harness but wrong for a row produced by ``manage.py aieval --provider
openai``: the model id already names the vendor. Re-derive the provider from the
catalog for every row whose model belongs to another provider.

Reverse is a no-op — the pre-0002 rows carried no provider to restore.
"""

from django.db import migrations


def _backfill_provider_from_catalog(apps, schema_editor):
    from apps.ai.catalog import list_models

    EvalRun = apps.get_model("analytics", "EvalRun")
    for model_info in list_models():
        if model_info.provider == "claude":
            continue
        EvalRun.objects.filter(model=model_info.id).update(provider=model_info.provider)


class Migration(migrations.Migration):
    dependencies = [
        ("analytics", "0002_evalrun_provider"),
    ]

    operations = [
        migrations.RunPython(_backfill_provider_from_catalog, migrations.RunPython.noop),
    ]

from django.db import migrations

from apps.snapshots.migrations._backfill import populate


def forwards(apps, schema_editor):
    populate(
        apps.get_model("snapshots", "Snapshot"),
        apps.get_model("snapshots", "SnapshotSection"),
    )


def backwards(apps, schema_editor):
    apps.get_model("snapshots", "Snapshot").objects.update(primary_ticker=None)


class Migration(migrations.Migration):
    dependencies = [("snapshots", "0007_snapshot_primary_ticker")]
    operations = [migrations.RunPython(forwards, backwards)]

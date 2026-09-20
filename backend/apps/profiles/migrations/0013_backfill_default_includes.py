from __future__ import annotations

from django.db import migrations

from apps.profiles.migrations._backfill import add_kinds


class Migration(migrations.Migration):
    dependencies = [
        ("profiles", "0012_alter_watchlistsymbol_watchlist"),
    ]

    operations = [
        migrations.RunPython(add_kinds, migrations.RunPython.noop),
    ]

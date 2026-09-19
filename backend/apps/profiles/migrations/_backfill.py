"""Shared by the backfill migration and its tests. Literal list on purpose —
migrations must not read the live model constant."""

KINDS = ["quotes", "positions", "breadth", "ohlc", "chain", "news", "events", "macro"]


def add_kinds(apps, schema_editor) -> None:
    TradingProfile = apps.get_model("profiles", "TradingProfile")
    for p in TradingProfile.objects.all():
        includes = list(p.default_includes or [])
        missing = [k for k in KINDS if k not in includes]
        if missing:
            p.default_includes = includes + missing
            p.save(update_fields=["default_includes"])

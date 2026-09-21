"""Shared by the capability-default migration and its tests. Literal field names on
purpose — migrations must not read the live model."""

FLAGS = ["enable_tools", "enable_thinking", "enable_memory"]


def enable_capabilities(apps, schema_editor) -> None:
    """Turn the AI capability flags on for profiles that predate the new defaults.

    Reverse is a no-op: the pre-migration per-row values are not recorded anywhere, so
    unapplying cannot distinguish a row this function flipped from one already True.
    """
    TradingProfile = apps.get_model("profiles", "TradingProfile")
    for flag in FLAGS:
        TradingProfile.objects.filter(**{flag: False}).update(**{flag: True})

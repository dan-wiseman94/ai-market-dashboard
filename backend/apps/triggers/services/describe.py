"""Format a matched_values dict into a human-readable string for notifications."""

from __future__ import annotations


def describe(matched_values: dict[str, float | None]) -> str:
    parts: list[str] = []
    for key, value in matched_values.items():
        if value is None or key.startswith("_prior:"):
            continue
        parts.append(_format_one(key, value))
    return ", ".join(parts)


def _format_one(key: str, value: float) -> str:
    if key.startswith("price:"):
        _, ticker = key.split(":", 1)
        return f"{ticker}={value:.2f}"
    if key.startswith("pct_change:"):
        _, ticker, window = key.split(":")
        sign = "+" if value >= 0 else ""
        return f"{ticker} {sign}{value * 100:.2f}% / {window}"
    if key.startswith("volume_z:"):
        _, ticker, window = key.split(":")
        return f"{ticker} vol z={value:.2f} / {window}"
    if key == "vix":
        return f"vix={value:.2f}"
    if key == "position_pl":
        return f"position_pl={value:.2f}"
    if key == "position_pl_pct":
        sign = "+" if value >= 0 else ""
        return f"position_pl {sign}{value * 100:.2f}%"
    if key.startswith("days_to_earnings:"):
        _, ticker = key.split(":", 1)
        return f"{ticker} earnings in {int(value)}d"
    return f"{key}={value}"

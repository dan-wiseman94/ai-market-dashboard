"""Condition DSL validator.

Called from EventTrigger.clean() and the DRF serializer. Keeps invalid JSON
out of the database and returns user-facing error paths like ".all[1].op".
"""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError

VALID_METRICS = {
    "price",
    "pct_change",
    "volume_z",
    "vix",
    "position_pl",
    "position_pl_pct",
    "days_to_earnings",
}
VALID_OPS = {">", ">=", "<", "<=", "==", "crosses_above", "crosses_below"}
VALID_WINDOWS = {"1m", "5m", "15m", "1h", "1d"}
TICKER_REQUIRED = {"price", "pct_change", "volume_z", "days_to_earnings"}
WINDOW_REQUIRED = {"pct_change", "volume_z"}
NON_CROSSING_METRICS = {"days_to_earnings"}
LEAF_KEYS = {"metric", "ticker", "op", "value", "window"}


def validate_condition(node: Any, *, path: str = "") -> None:
    """Recurse the tree. Raises ValidationError with path on any invalid shape."""
    if not isinstance(node, dict):
        raise ValidationError(f"{path or '<root>'}: expected object, got {type(node).__name__}")

    # Group nodes
    for key in ("all", "any"):
        if key in node:
            if len(node) != 1:
                raise ValidationError(f"{path}.{key}: group node must have only '{key}' key")
            children = node[key]
            if not isinstance(children, list):
                raise ValidationError(f"{path}.{key}: must be a list")
            for i, child in enumerate(children):
                validate_condition(child, path=f"{path}.{key}[{i}]")
            return

    if "not" in node:
        if len(node) != 1:
            raise ValidationError(f"{path}.not: must have only 'not' key")
        child = node["not"]
        if isinstance(child, list):
            raise ValidationError(f"{path}.not: must wrap a single node, got list")
        validate_condition(child, path=f"{path}.not")
        return

    # Leaf node — reject typo'd/unknown keys (windoww, tikcer, etc.) so a rule
    # that "looks right" can't be silently evaluated with missing fields.
    extra_keys = set(node.keys()) - LEAF_KEYS
    if extra_keys:
        raise ValidationError(f"{path}: unknown leaf keys {sorted(extra_keys)!r}")

    metric = node.get("metric")
    if metric not in VALID_METRICS:
        raise ValidationError(f"{path}.metric: unknown metric {metric!r}")
    op = node.get("op")
    if op not in VALID_OPS:
        raise ValidationError(f"{path}.op: unknown operator {op!r}")
    value = node.get("value")
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise ValidationError(f"{path}.value: must be a number")
    if metric in NON_CROSSING_METRICS and op in ("crosses_above", "crosses_below"):
        raise ValidationError(f"{path}.op: crossing ops not supported for metric {metric!r}")
    if metric in TICKER_REQUIRED:
        ticker = node.get("ticker")
        if not isinstance(ticker, str) or not ticker:
            raise ValidationError(f"{path}.ticker: required non-empty string for metric {metric!r}")
    window = node.get("window")
    if metric in WINDOW_REQUIRED and window is None:
        raise ValidationError(f"{path}.window: required for metric {metric!r}")
    if metric not in WINDOW_REQUIRED and window is not None:
        raise ValidationError(f"{path}.window: not allowed for metric {metric!r}")
    if window is not None and window not in VALID_WINDOWS:
        raise ValidationError(f"{path}.window: {window!r} is not a valid window")


def tickers_in_condition(node: Any) -> set[str]:
    """Collect all leaf `ticker` values from a (validated or raw) condition tree."""
    out: set[str] = set()
    if not isinstance(node, dict):
        return out
    for key in ("all", "any"):
        if key in node and isinstance(node[key], list):
            for child in node[key]:
                out |= tickers_in_condition(child)
            return out
    if "not" in node:
        return tickers_in_condition(node["not"])
    ticker = node.get("ticker")
    if isinstance(ticker, str) and ticker:
        out.add(ticker)
    return out

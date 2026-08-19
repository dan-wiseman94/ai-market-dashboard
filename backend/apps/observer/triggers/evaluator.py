"""Pure evaluator for the trigger condition DSL.

No I/O: takes a MetricsSnapshot dict literal and returns (matched, matched_values).
matched_values records every metric key the evaluator read during this call —
used to populate TriggerFiring.matched_values and the notification body.
"""

from __future__ import annotations

import operator
from collections.abc import Mapping
from typing import Any

MetricsSnapshot = Mapping[str, float | None]

_COMPARE_OPS = {
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
    "==": operator.eq,
}
CROSSING_OPS = ("crosses_above", "crosses_below")


def evaluate(node: dict, metrics: MetricsSnapshot) -> tuple[bool, dict[str, float | None]]:
    """Recurse the tree; return (matched, matched_values_this_call)."""
    values: dict[str, float | None] = {}
    matched = _eval_node(node, metrics, values)
    return matched, values


def _eval_node(node: dict, metrics: MetricsSnapshot, values: dict) -> bool:
    if "all" in node:
        return all(_eval_node(child, metrics, values) for child in node["all"])
    if "any" in node:
        return any(_eval_node(child, metrics, values) for child in node["any"])
    if "not" in node:
        return not _eval_node(node["not"], metrics, values)
    return _eval_leaf(node, metrics, values)


_INDICATOR_KEY_PARAMS = {
    "rsi": ("period",),
    "atr_pct": ("period",),
    "dist_from_sma_pct": ("period",),
    "sma_spread_pct": ("fast", "slow"),
    "dist_from_52w_high": (),
    "dist_from_52w_low": (),
    "gap_pct": (),
}


def leaf_key(node: dict) -> str:
    metric = node["metric"]
    if metric == "vix":
        return "vix"
    if metric.startswith("position_"):
        return metric
    if metric == "pct_change":
        return f"pct_change:{node['ticker']}:{node['window']}"
    if metric == "volume_z":
        return f"volume_z:{node['ticker']}:{node['window']}"
    if metric == "days_to_earnings":
        return f"days_to_earnings:{node['ticker']}"
    if metric in {"pe_ratio", "market_cap", "revenue_growth", "gross_margin"}:
        return f"{metric}:{node['ticker']}"
    if metric in _INDICATOR_KEY_PARAMS:
        params = node.get("params") or {}
        parts = [metric, node["ticker"]]
        if node.get("window"):
            parts.append(node["window"])
        parts += [str(params.get(pk)) for pk in _INDICATOR_KEY_PARAMS[metric]]
        return ":".join(parts)
    return f"price:{node['ticker']}"


def iter_leaves(condition: Any) -> list[dict]:
    """Return every leaf (metric) node in a condition tree, in document order.

    Shared by metrics.build_snapshot and backtest so the DSL is walked one way.
    """
    leaves: list[dict] = []

    def _walk(node: Any) -> None:
        if not isinstance(node, dict):
            return
        if "all" in node:
            for child in node["all"]:
                _walk(child)
        elif "any" in node:
            for child in node["any"]:
                _walk(child)
        elif "not" in node:
            _walk(node["not"])
        elif "metric" in node:
            leaves.append(node)

    _walk(condition or {})
    return leaves


def _eval_leaf(node: dict, metrics: MetricsSnapshot, values: dict) -> bool:
    key = leaf_key(node)
    current = metrics.get(key)
    values[key] = current
    op = node["op"]
    if op in _COMPARE_OPS:
        if current is None:
            return False
        return bool(_COMPARE_OPS[op](current, node["value"]))
    if op in CROSSING_OPS:
        prior_key = f"_prior:{key}"
        prior = metrics.get(prior_key)
        values[prior_key] = prior
        if current is None or prior is None:
            return False
        threshold = node["value"]
        if op == "crosses_above":
            return prior <= threshold < current
        return prior >= threshold > current
    raise ValueError(f"unknown op {op!r}")

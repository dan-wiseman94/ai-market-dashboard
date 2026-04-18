"""Pure evaluator for the trigger condition DSL.

No I/O: takes a MetricsSnapshot dict literal and returns (matched, matched_values).
matched_values records every metric key the evaluator read during this call —
used to populate TriggerFiring.matched_values and the notification body.
"""
from __future__ import annotations

import operator
from collections.abc import Mapping

MetricsSnapshot = Mapping[str, float | None]

_COMPARE_OPS = {
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
    "==": operator.eq,
}


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


def _leaf_key(node: dict) -> str:
    metric = node["metric"]
    if metric == "vix":
        return "vix"
    if metric.startswith("position_"):
        return metric
    if metric == "pct_change":
        return f"pct_change:{node['ticker']}:{node['window']}"
    # price
    return f"price:{node['ticker']}"


def _eval_leaf(node: dict, metrics: MetricsSnapshot, values: dict) -> bool:
    key = _leaf_key(node)
    current = metrics.get(key)
    values[key] = current
    if current is None:
        return False
    op = node["op"]
    if op in _COMPARE_OPS:
        return bool(_COMPARE_OPS[op](current, node["value"]))
    # Crossing ops come in Task 6; raise so tests don't silently pass yet.
    raise NotImplementedError(f"op {op} not implemented")

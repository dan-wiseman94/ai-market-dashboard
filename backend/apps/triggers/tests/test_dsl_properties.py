"""Property-based tests for the trigger condition DSL (apps.triggers.evaluator).

Pure evaluator — no DB. These structural identities must hold for ANY leaf truth
value, so we drive the leaf via a `vix` metric the test controls.
"""

from hypothesis import given
from hypothesis import strategies as st

from apps.triggers.evaluator import evaluate

_OPS = st.sampled_from([">", ">=", "<", "<=", "=="])
_NUM = st.floats(allow_nan=False, allow_infinity=False, min_value=-1e6, max_value=1e6)


def _leaf(op, value):
    return {"metric": "vix", "op": op, "value": value}


def _metrics(vix):
    return {} if vix is None else {"vix": vix}


@given(op=_OPS, value=_NUM, vix=st.one_of(st.none(), _NUM))
def test_single_child_all_and_any_equal_the_leaf(op, value, vix):
    leaf, metrics = _leaf(op, value), _metrics(vix)
    base = evaluate(leaf, metrics)[0]
    assert evaluate({"all": [leaf]}, metrics)[0] == base
    assert evaluate({"any": [leaf]}, metrics)[0] == base


@given(op=_OPS, value=_NUM, vix=st.one_of(st.none(), _NUM))
def test_double_negation_is_identity(op, value, vix):
    leaf, metrics = _leaf(op, value), _metrics(vix)
    base = evaluate(leaf, metrics)[0]
    assert evaluate({"not": {"not": leaf}}, metrics)[0] == base


def test_vacuous_all_is_true_and_vacuous_any_is_false():
    assert evaluate({"all": []}, {})[0] is True
    assert evaluate({"any": []}, {})[0] is False


@given(op_a=_OPS, val_a=_NUM, op_b=_OPS, val_b=_NUM, vix=st.one_of(st.none(), _NUM))
def test_de_morgan(op_a, val_a, op_b, val_b, vix):
    a, b, metrics = _leaf(op_a, val_a), _leaf(op_b, val_b), _metrics(vix)
    not_all = evaluate({"not": {"all": [a, b]}}, metrics)[0]
    any_not = evaluate({"any": [{"not": a}, {"not": b}]}, metrics)[0]
    assert not_all == any_not

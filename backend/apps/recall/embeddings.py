"""Local embedding backend (fastembed). Returns None when unavailable → FTS fallback."""

from __future__ import annotations

import logging

import numpy as np

log = logging.getLogger(__name__)
MODEL_NAME = "BAAI/bge-small-en-v1.5"
DIM = 384
_model = None
_tried = False


def _get_model():
    global _model, _tried
    if _model is None and not _tried:
        _tried = True
        try:
            from fastembed import TextEmbedding

            _model = TextEmbedding(model_name=MODEL_NAME)
        except Exception as exc:  # import error, model missing, etc.
            log.warning("recall.embed unavailable: %s", exc)
            _model = None
    return _model


def embed(texts: list[str]) -> list[list[float]] | None:
    model = _get_model()
    if model is None or not texts:
        return None if model is None else []
    try:
        return [np.asarray(v, dtype=float).tolist() for v in model.embed(list(texts))]
    except Exception as exc:
        log.warning("recall.embed failed: %s", exc)
        return None

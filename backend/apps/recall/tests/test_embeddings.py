from apps.recall import embeddings


def test_embed_returns_vectors(monkeypatch):
    class FakeModel:
        def embed(self, texts):
            return [[0.0] * 384 for _ in texts]

    monkeypatch.setattr(embeddings, "_get_model", lambda: FakeModel())
    out = embeddings.embed(["a", "b"])
    assert out is not None and len(out) == 2 and len(out[0]) == 384


def test_embed_none_when_backend_unavailable(monkeypatch):
    monkeypatch.setattr(embeddings, "_get_model", lambda: None)
    assert embeddings.embed(["a"]) is None

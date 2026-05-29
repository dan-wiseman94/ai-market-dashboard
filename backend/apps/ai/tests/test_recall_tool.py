import pytest

from apps.ai.tools.registry import default_toolset


@pytest.mark.django_db
def test_recall_tool_registered(monkeypatch):
    import apps.recall.services.search as S

    monkeypatch.setattr(
        S,
        "search",
        lambda q, **k: [{"kind": "thesis", "object_id": 1, "snippet": "NVDA", "link": "/theses/1"}],
    )
    ts = default_toolset()
    out = ts.run("recall", {"query": "nvda"})
    assert out["ok"] and out["result"][0]["object_id"] == 1

import pytest

playwright = pytest.importorskip("playwright")
from apps.snapshots.models import SnapshotImage  # noqa: E402

pytestmark = pytest.mark.integration


@pytest.mark.django_db
def test_render_chart_png_returns_real_png_bytes(settings):
    """Requires the worker image with chromium, and the frontend service running.

    Skip locally with: pytest -m 'not integration'.
    """
    from apps.snapshots.services.render import render_chart_png

    settings.RENDER_BASE_URL = "http://frontend:5173"
    img = render_chart_png("SPY", "5m", 10, snapshot_id=None)

    assert isinstance(img, SnapshotImage)
    # C7: render offloads bytes to the /data volume (data=None), so read via the helper.
    from apps.snapshots.image_store import read_image_bytes

    assert read_image_bytes(img).startswith(b"\x89PNG")

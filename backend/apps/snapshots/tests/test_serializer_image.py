import pytest
from apps.profiles.models import TradingProfile
from apps.snapshots.models import Snapshot, SnapshotImage
from apps.snapshots.serializer import build_image_blocks, _render_image


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 50


@pytest.fixture
def two_images(db):
    profile = TradingProfile.objects.create(name="P", style="x")
    snap = Snapshot.objects.create(profile=profile, includes=["image"])
    a = SnapshotImage.objects.create(snapshot=snap, kind="server_render", data=PNG, caption="SPY 5m, 60 bars")
    b = SnapshotImage.objects.create(snapshot=snap, kind="client_capture", data=PNG, caption="TSLA 1h")
    return [a.id, b.id]


@pytest.mark.django_db
def test_build_image_blocks_claude(two_images):
    blocks = build_image_blocks(two_images, provider_name="claude")
    assert len(blocks) == 2
    assert blocks[0]["type"] == "image"
    assert blocks[0]["source"]["type"] == "base64"
    assert blocks[0]["source"]["media_type"] == "image/png"
    assert blocks[0]["source"]["data"]


@pytest.mark.django_db
def test_build_image_blocks_openai(two_images):
    blocks = build_image_blocks(two_images, provider_name="openai")
    assert len(blocks) == 2
    assert blocks[0]["type"] == "image_url"
    assert blocks[0]["image_url"]["url"].startswith("data:image/png;base64,")


@pytest.mark.django_db
def test_render_image_lists_captions(two_images):
    md = _render_image({"image_ids": two_images})
    assert "## Charts attached" in md
    assert "SPY 5m, 60 bars (server-rendered)" in md
    assert "TSLA 1h (your screenshot)" in md

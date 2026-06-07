"""Server-side chart rendering via Playwright."""

from __future__ import annotations

from urllib.parse import urlencode

from asgiref.sync import async_to_sync
from django.conf import settings

from apps.snapshots.image_store import create_image
from apps.snapshots.models import SnapshotImage


def _build_url(ticker: str, timeframe: str, bars: int) -> str:
    base = settings.RENDER_BASE_URL.rstrip("/")
    qs = urlencode({"ticker": ticker, "timeframe": timeframe, "bars": bars})
    if base.endswith(".html") or "/static/" in base:
        return f"{base}#/render/chart?{qs}"  # prod hash route
    return f"{base}/render/chart?{qs}"  # dev path route


async def _render_async(url: str) -> bytes:
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = await browser.new_page(viewport={"width": 1200, "height": 700})
            await page.goto(url, wait_until="networkidle", timeout=20000)
            await page.wait_for_selector("body[data-render-ready='true']", timeout=15000)
            chart = await page.locator("#chart-root").element_handle()
            if chart is None:
                raise RuntimeError("#chart-root not found in rendered page")
            return await chart.screenshot(type="png")
        finally:
            await browser.close()


def render_chart_png(
    ticker: str,
    timeframe: str,
    bars: int,
    *,
    snapshot_id: int | None,
) -> SnapshotImage:
    url = _build_url(ticker, timeframe, bars)
    png = async_to_sync(_render_async)(url)
    return create_image(
        snapshot_id=snapshot_id,
        kind="server_render",
        data=png,
        caption=f"{ticker} {timeframe}, {bars} bars",
    )

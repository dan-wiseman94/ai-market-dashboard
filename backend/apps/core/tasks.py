"""Smoke-test Celery tasks."""

from __future__ import annotations

from celery import shared_task


@shared_task(name="core.ping")
def ping(name: str | None = None) -> str:
    """Return 'pong' or 'pong <name>'. Used to verify Celery end-to-end."""
    return "pong" if name is None else f"pong {name}"

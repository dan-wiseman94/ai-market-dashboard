"""Shared Channels group-broadcast helpers.

One home for the ``get_channel_layer() -> group_send`` dance the thread,
snapshot, and notification broadcasters all repeat. Each app keeps its thin
``_broadcast`` wrapper (which knows its group name + envelope type, and is the
seam tests patch); only the layer plumbing lives here.
"""

from __future__ import annotations

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


def group_broadcast(group: str, message_type: str, payload: dict) -> None:
    layer = get_channel_layer()
    if layer is None:
        return
    async_to_sync(layer.group_send)(group, {"type": message_type, "payload": payload})


async def group_broadcast_async(group: str, message_type: str, payload: dict) -> None:
    layer = get_channel_layer()
    if layer is None:
        return
    await layer.group_send(group, {"type": message_type, "payload": payload})

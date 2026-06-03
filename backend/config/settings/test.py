"""Test settings — dev plus an in-process channel layer.

pytest-randomly reorders tests; with channels_redis, one async test's Redis
connection can bind to a now-closed event loop and break a *later* async test's
teardown (`group_discard` during WebsocketCommunicator.disconnect). The in-memory
layer holds no cross-loop connection state, so the order-dependent flake goes
away. The e2e stack (compose.e2e.yaml) still exercises the real Redis layer.
"""

from .dev import *

CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

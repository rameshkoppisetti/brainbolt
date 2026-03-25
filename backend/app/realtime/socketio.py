from __future__ import annotations

import socketio


sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")


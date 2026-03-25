from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import socketio

from app.config import settings
from app.http.routes import router as api_router
from app.realtime.socketio import sio


fastapi_app = FastAPI(title="BrainBolt API", version="0.1.0")

fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.cors_origin] if settings.cors_origin != "*" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@fastapi_app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


fastapi_app.include_router(api_router, prefix="/v1")

# Expose a single ASGI app that serves both HTTP and WebSocket (Socket.IO).
app = socketio.ASGIApp(sio, other_asgi_app=fastapi_app)


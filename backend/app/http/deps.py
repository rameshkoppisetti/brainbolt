from __future__ import annotations

from collections.abc import Generator
from typing import Optional

import redis
from fastapi import Request
from sqlalchemy.orm import Session

from app.core.redis_client import get_redis
from app.db.engine import SessionLocal


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_redis_client() -> redis.Redis:
    return get_redis()


def get_request_id(request: Request) -> Optional[str]:
    return request.headers.get("x-request-id")


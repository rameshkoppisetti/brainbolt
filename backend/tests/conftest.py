from __future__ import annotations

import hashlib
from collections.abc import Generator

import fakeredis
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.models import Question
from app.http import deps
from app.main import fastapi_app


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


@pytest.fixture()
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    try:
        # Seed a minimal question set across difficulties.
        db.add_all(
            [
                Question(
                    id="q-1",
                    difficulty=1,
                    prompt="What is 2 + 2?",
                    choices=["1", "2", "3", "4"],
                    correct_answer_hash=sha256("4"),
                    tags=["math"],
                ),
                Question(
                    id="q-2",
                    difficulty=2,
                    prompt="Which data structure is FIFO?",
                    choices=["Stack", "Queue", "Tree", "Graph"],
                    correct_answer_hash=sha256("Queue"),
                    tags=["cs"],
                ),
                Question(
                    id="q-3",
                    difficulty=3,
                    prompt="Binary search is?",
                    choices=["O(1)", "O(log n)", "O(n)", "O(n log n)"],
                    correct_answer_hash=sha256("O(log n)"),
                    tags=["algorithms"],
                ),
                # Second easy question so /next can avoid immediate repeat at difficulty 1.
                Question(
                    id="q-1b",
                    difficulty=1,
                    prompt="What is 3 + 3?",
                    choices=["5", "6", "7", "8"],
                    correct_answer_hash=sha256("6"),
                    tags=["math"],
                ),
            ]
        )
        db.commit()
        yield db
    finally:
        db.close()


@pytest.fixture()
def redis_client():
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture()
def client(db_session: Session, redis_client) -> Generator[TestClient, None, None]:
    def _get_db_override() -> Generator[Session, None, None]:
        yield db_session

    def _get_redis_override():
        return redis_client

    fastapi_app.dependency_overrides[deps.get_db] = _get_db_override
    fastapi_app.dependency_overrides[deps.get_redis_client] = _get_redis_override

    with TestClient(fastapi_app) as c:
        yield c

    fastapi_app.dependency_overrides.clear()


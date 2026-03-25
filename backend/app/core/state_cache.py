from __future__ import annotations

import json
from typing import Any
from typing import Optional

import redis

from app.db.models import UserState


def user_state_key(user_id: str) -> str:
    return f"user_state:{user_id}"


def get_cached_user_state(r: redis.Redis, user_id: str) -> Optional[dict[str, Any]]:
    raw = r.get(user_state_key(user_id))
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def set_cached_user_state(r: redis.Redis, state: UserState, *, ttl_seconds: int = 3600) -> None:
    payload = {
        "user_id": state.user_id,
        "current_difficulty": int(state.current_difficulty),
        "current_question_id": state.current_question_id,
        "streak": int(state.streak),
        "max_streak": int(state.max_streak),
        "total_score": int(state.total_score),
        "last_question_id": state.last_question_id,
        "last_answer_at": state.last_answer_at.isoformat() if state.last_answer_at else None,
        "ema_accuracy": float(state.ema_accuracy),
        "answered_count": int(state.answered_count),
        "correct_count": int(state.correct_count),
        "state_version": int(state.state_version),
    }
    r.set(user_state_key(state.user_id), json.dumps(payload), ex=ttl_seconds)


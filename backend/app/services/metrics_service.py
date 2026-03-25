from __future__ import annotations

import redis
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import AnswerLog, UserState
from app.http.schemas import MetricsResponse
from app.services.errors import UserNotFound
from app.services.quiz_service import metrics_key


def get_metrics(*, user_id: str, db: Session, r: redis.Redis) -> MetricsResponse:
    key = metrics_key(user_id)
    cached = r.get(key)
    if cached:
        return MetricsResponse.model_validate_json(cached)

    state = db.get(UserState, user_id)
    if not state:
        raise UserNotFound()

    rows = (
        db.execute(
            select(AnswerLog.difficulty, func.count(AnswerLog.id))
            .where(AnswerLog.user_id == user_id)
            .group_by(AnswerLog.difficulty)
        )
        .all()
    )
    histogram = {int(d): int(c) for (d, c) in rows}
    recent = (
        db.execute(
            select(AnswerLog.correct)
            .where(AnswerLog.user_id == user_id)
            .order_by(AnswerLog.answered_at.desc())
            .limit(20)
        )
        .scalars()
        .all()
    )

    answered = int(state.answered_count)
    correct = int(state.correct_count)
    accuracy = (correct / answered) if answered else 0.0

    resp = MetricsResponse(
        currentDifficulty=int(state.current_difficulty),
        streak=int(state.streak),
        maxStreak=int(state.max_streak),
        totalScore=int(state.total_score),
        accuracy=float(accuracy),
        difficultyHistogram=histogram,
        recentPerformance=[bool(x) for x in recent],
    )
    r.set(key, resp.model_dump_json(), ex=settings.metrics_cache_ttl_seconds)
    return resp


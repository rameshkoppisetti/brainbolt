from __future__ import annotations

import redis
from typing import Optional, Tuple

from app.http.schemas import LeaderboardEntry
from app.services.quiz_service import lb_score_key, lb_streak_key


def top_scores(r: redis.Redis, *, n: int) -> list[LeaderboardEntry]:
    items = r.zrevrange(lb_score_key(), 0, n - 1, withscores=True)
    return [LeaderboardEntry(userId=str(uid), score=int(score)) for uid, score in items]


def top_streaks(r: redis.Redis, *, n: int) -> list[LeaderboardEntry]:
    items = r.zrevrange(lb_streak_key(), 0, n - 1, withscores=True)
    return [LeaderboardEntry(userId=str(uid), score=int(score)) for uid, score in items]


def your_score_rank(r: redis.Redis, *, user_id: str) -> Tuple[Optional[int], Optional[int]]:
    rank = r.zrevrank(lb_score_key(), user_id)
    score = r.zscore(lb_score_key(), user_id)
    return (int(rank) + 1) if rank is not None else None, int(score) if score is not None else None


def your_streak_rank(r: redis.Redis, *, user_id: str) -> Tuple[Optional[int], Optional[int]]:
    rank = r.zrevrank(lb_streak_key(), user_id)
    score = r.zscore(lb_streak_key(), user_id)
    return (int(rank) + 1) if rank is not None else None, int(score) if score is not None else None


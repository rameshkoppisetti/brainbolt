from __future__ import annotations

import redis
from fastapi import APIRouter, Depends, Query

from app.http.deps import get_redis_client
from app.http.schemas import LeaderboardEntry, LeaderboardResponse
from app.services.leaderboard_service import (
    top_scores,
    top_streaks,
    your_score_rank,
    your_streak_rank,
)


router = APIRouter()


@router.get("/score", response_model=LeaderboardResponse)
def leaderboard_score(
    userId: str = Query(...),
    n: int = Query(10, ge=1, le=100),
    r: redis.Redis = Depends(get_redis_client),
) -> LeaderboardResponse:
    top = top_scores(r, n=n)
    yourRank, yourScore = your_score_rank(r, user_id=userId)
    return LeaderboardResponse(top=top, yourRank=yourRank, yourScore=yourScore)


@router.get("/streak", response_model=LeaderboardResponse)
def leaderboard_streak(
    userId: str = Query(...),
    n: int = Query(10, ge=1, le=100),
    r: redis.Redis = Depends(get_redis_client),
) -> LeaderboardResponse:
    top = top_streaks(r, n=n)
    yourRank, yourScore = your_streak_rank(r, user_id=userId)
    return LeaderboardResponse(top=top, yourRank=yourRank, yourScore=yourScore)


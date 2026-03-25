from __future__ import annotations

from fastapi import APIRouter

from app.http.routes_leaderboard import router as leaderboard_router
from app.http.routes_quiz import router as quiz_router


router = APIRouter()
router.include_router(quiz_router, prefix="/quiz", tags=["quiz"])
router.include_router(leaderboard_router, prefix="/leaderboard", tags=["leaderboard"])


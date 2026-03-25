from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, TypedDict

from app.http.schemas import SubmitAnswerResponse


class LeaderboardEntryPayload(TypedDict):
    userId: str
    score: int


class ChangedUserPayload(TypedDict):
    userId: str
    totalScore: int
    streak: int
    currentDifficulty: int
    rankScore: Optional[int]
    rankStreak: Optional[int]


class LeaderboardUpdatePayload(TypedDict):
    type: str
    changedUser: ChangedUserPayload
    topScore: list[LeaderboardEntryPayload]
    topStreak: list[LeaderboardEntryPayload]


@dataclass(frozen=True)
class SubmitAnswerResult:
    """
    Service contract for submit-answer:
    - response: what REST returns
    - emitted_payload: optional websocket broadcast payload (None on idempotent cache hit)
    """

    response: SubmitAnswerResponse
    emitted_payload: Optional[LeaderboardUpdatePayload]


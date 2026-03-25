from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class NextQuestionResponse(BaseModel):
    questionId: str
    difficulty: int = Field(description="Question tier in the bank (drives score deltas).")
    userDifficulty: int = Field(description="Adaptive band in user_state (what /next targeted).")
    prompt: str
    choices: list[str]
    sessionId: str
    stateVersion: int
    currentScore: int
    currentStreak: int


class SubmitAnswerRequest(BaseModel):
    userId: str
    sessionId: str
    questionId: str
    answer: str
    stateVersion: int
    answerIdempotencyKey: str = Field(min_length=1, max_length=200)


class SubmitAnswerResponse(BaseModel):
    correct: bool
    newDifficulty: int
    newStreak: int
    scoreDelta: int
    totalScore: int
    stateVersion: int
    leaderboardRankScore: Optional[int]
    leaderboardRankStreak: Optional[int]


class MetricsResponse(BaseModel):
    currentDifficulty: int
    streak: int
    maxStreak: int
    totalScore: int
    accuracy: float
    difficultyHistogram: dict[int, int]
    recentPerformance: list[bool]


class LeaderboardEntry(BaseModel):
    userId: str
    score: int


class LeaderboardResponse(BaseModel):
    top: list[LeaderboardEntry]
    yourRank: Optional[int]
    yourScore: Optional[int]


from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Float,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    state: Mapped["UserState"] = relationship(back_populates="user", uselist=False)


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    difficulty: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    choices: Mapped[dict] = mapped_column(JSON, nullable=False)
    correct_answer_hash: Mapped[str] = mapped_column(String, nullable=False)
    tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("difficulty >= 1 AND difficulty <= 10", name="questions_difficulty_bounds"),
    )


class UserState(Base):
    __tablename__ = "user_state"

    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    current_difficulty: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    current_question_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("questions.id", ondelete="SET NULL"), nullable=True
    )
    streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_score: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    last_question_id: Mapped[Optional[str]] = mapped_column(String, ForeignKey("questions.id"), nullable=True)
    last_answer_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ema_accuracy: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    answered_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    correct_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    state_version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    user: Mapped["User"] = relationship(back_populates="state")

    __table_args__ = (
        CheckConstraint("current_difficulty >= 1 AND current_difficulty <= 10", name="user_state_difficulty_bounds"),
        CheckConstraint("streak >= 0", name="user_state_streak_nonneg"),
        CheckConstraint("max_streak >= 0", name="user_state_max_streak_nonneg"),
    )


class AnswerLog(Base):
    __tablename__ = "answer_log"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    question_id: Mapped[str] = mapped_column(String, ForeignKey("questions.id"), nullable=False)
    difficulty: Mapped[int] = mapped_column(Integer, nullable=False)
    answer: Mapped[str] = mapped_column(String, nullable=False)
    correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    score_delta: Mapped[int] = mapped_column(Integer, nullable=False)
    streak_at_answer: Mapped[int] = mapped_column(Integer, nullable=False)
    answered_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    state_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    answer_idempotency_key: Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "question_id", name="answer_log_user_question_uq"),
        UniqueConstraint("user_id", "answer_idempotency_key", name="answer_log_user_idempotency_uq"),
        Index("answer_log_user_time_idx", "user_id", "answered_at"),
        Index("answer_log_user_question_idx", "user_id", "question_id"),
        CheckConstraint("difficulty >= 1 AND difficulty <= 10", name="answer_log_difficulty_bounds"),
    )


class LeaderboardScore(Base):
    __tablename__ = "leaderboard_score"
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    total_score: Mapped[int] = mapped_column(BigInteger, nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class LeaderboardStreak(Base):
    __tablename__ = "leaderboard_streak"
    user_id: Mapped[str] = mapped_column(String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    max_streak: Mapped[int] = mapped_column(Integer, nullable=False)
    current_streak: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


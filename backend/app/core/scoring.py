from __future__ import annotations

import math

from app.config import settings


def clamp_int(x: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, x))


def streak_multiplier(streak: int) -> float:
    # Linear ramp: 0->1.0, 1->1.0, 2->2.0, ... capped
    return float(min(max(1, streak), settings.max_streak_multiplier))


def difficulty_weight(difficulty: int) -> int:
    # MVP: weight grows with difficulty but not explosively.
    return 10 * difficulty


def score_delta_for_answer(*, difficulty: int, correct: bool, streak_after: int) -> int:
    if not correct:
        # Penalty scales with difficulty level played.
        return -abs(int(settings.wrong_penalty_per_difficulty)) * int(difficulty)
    base = difficulty_weight(difficulty)
    mult = streak_multiplier(streak_after)
    return int(math.floor(base * mult))


def next_difficulty_on_correct(*, current: int) -> int:
    """Raise band after a correct answer, from the card's difficulty (misses use quiz_service._difficulty_after_wrong)."""
    return clamp_int(int(current) + 1, 1, 10)


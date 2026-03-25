from __future__ import annotations

import hashlib
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import redis
from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.scoring import next_difficulty_on_correct, score_delta_for_answer
from app.core.state_cache import get_cached_user_state, set_cached_user_state
from app.db.engine import SessionLocal
from app.db.models import AnswerLog, Question, User, UserState
from app.http.schemas import NextQuestionResponse, SubmitAnswerRequest, SubmitAnswerResponse
from app.services.errors import (
    NoEligibleQuestionsError,
    NoQuestionsError,
    NotCurrentQuestion,
    QuestionAlreadyMastered,
    QuestionNotFound,
    StateVersionConflict,
)
from app.services.types import SubmitAnswerResult


def lb_score_key() -> str:
    return "lb:score"


def lb_streak_key() -> str:
    return "lb:streak"


def idem_key(user_id: str, idem: str) -> str:
    return f"idem:{user_id}:{idem}"


def metrics_key(user_id: str) -> str:
    return f"metrics:{user_id}"

def question_buffer_key(user_id: str) -> str:
    return f"question_buffer:{user_id}"


def question_buffer_refill_lock_key(user_id: str) -> str:
    return f"question_buffer:refill:{user_id}"


def seen_zset_key(user_id: str) -> str:
    return f"seen:{user_id}"


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def decay_streak_if_needed(state: UserState) -> None:
    if not state.last_answer_at:
        return
    last = state.last_answer_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    inactive_for = (utcnow() - last).total_seconds()
    if inactive_for >= settings.streak_decay_seconds:
        state.streak = 0


def ensure_user_state(db: Session, user_id: str) -> UserState:
    user = db.get(User, user_id)
    if not user:
        user = User(id=user_id)
        db.add(user)
        db.flush()

    state = db.get(UserState, user_id)
    if not state:
        state = UserState(user_id=user_id, current_difficulty=1, ema_accuracy=0.0)
        db.add(state)
        db.flush()
    return state


def _question_never_attempted_by(user_id: str):
    """
    Exclude questions this user has already submitted an answer for (correct or wrong).
    answer_log holds at most one row per (user, question); see _try_reserve_answer_log_row.
    """
    return ~exists(
        select(1).where(
            AnswerLog.user_id == user_id,
            AnswerLog.question_id == Question.id,
        )
    )


def _difficulties_with_eligible_future(
    db: Session, *, user_id: str, exclude_question_ids: Optional[set[str]] = None
) -> set[int]:
    """
    Difficulty levels that still have at least one never-attempted question,
    optionally excluding ids (e.g. the card about to be logged this request).
    """
    stmt = select(Question.difficulty).where(_question_never_attempted_by(user_id)).distinct()
    ex = exclude_question_ids or set()
    if ex:
        stmt = stmt.where(Question.id.not_in(tuple(ex)))
    return {int(x) for x in db.execute(stmt).scalars().all()}


def _difficulties_with_eligible(db: Session, *, user_id: str) -> set[int]:
    """Which difficulty buckets still have at least one never-attempted question."""
    return _difficulties_with_eligible_future(db, user_id=user_id, exclude_question_ids=None)


def _difficulty_after_wrong(
    db: Session,
    *,
    user_id: str,
    user_level: int,
    question: Question,
) -> int:
    """
    Lower the user's adaptive difficulty on a miss (never raise it because the card was hard).
    Only steps into a band that still has never-attempted questions after this answer is logged.
    """
    u = max(1, min(10, int(user_level)))
    eligible = _difficulties_with_eligible_future(db, user_id=user_id, exclude_question_ids={question.id})
    if not eligible:
        return u
    stepped = max(1, u - 1)
    at_or_below_step = [d for d in eligible if d <= stepped]
    if at_or_below_step:
        return max(at_or_below_step)
    strictly_easier = [d for d in eligible if d < u]
    if strictly_easier:
        return max(strictly_easier)
    at_or_below_user = [d for d in eligible if d <= u]
    if at_or_below_user:
        return max(at_or_below_user)
    return u


def _attempted_question_ids(db: Session, *, user_id: str) -> set[str]:
    """Membership set for Redis buffer pops."""
    rows = (
        db.execute(select(AnswerLog.question_id).where(AnswerLog.user_id == user_id).distinct())
        .scalars()
        .all()
    )
    return {str(x) for x in rows}


def _eligible_difficulties_desc(available: set[int]) -> list[int]:
    """Harder difficulties first (10 → 1) among ``available``."""
    return sorted((int(x) for x in available), reverse=True)


def _db_fallback_difficulty_order(target: int, available: set[int]) -> list[int]:
    """
    Try the adaptively chosen bucket first, then widen downward by difficulty (hardest remaining first).
    """
    t = int(target)
    if t in available:
        return [t] + _eligible_difficulties_desc(available - {t})
    return _eligible_difficulties_desc(available)


def _count_questions_at_difficulty(db: Session, *, difficulty: int) -> int:
    return int(
        db.execute(
            select(func.count()).select_from(Question).where(Question.difficulty == int(difficulty))
        ).scalar_one()
    )


def _should_avoid_last_question(db: Session, *, difficulty: int, last_question_id: Optional[str]) -> bool:
    if not last_question_id:
        return False
    return _count_questions_at_difficulty(db, difficulty=int(difficulty)) > 1


def _choose_available_difficulty(
    *,
    base_difficulty: int,
    streak: int,
    answered_count: int,
    available_difficulties: set[int],
) -> int:
    """
    Climb when possible without skipping bands we still have stock in:
    - First-ever serve (no answers): easiest tier >= adaptive band.
    - Later: hardest tier in [base, base+1] if any; else jump to the lowest tier still above base+1.
    If nothing remains >= base, use the hardest tier below base (lower buckets OK).

    ``streak`` is unused but kept for caller stability.
    """
    _ = streak
    if not available_difficulties:
        return max(1, min(10, int(base_difficulty)))
    base = max(1, min(10, int(base_difficulty)))
    av = available_difficulties
    at_or_above = sorted([d for d in av if d >= base])
    if not at_or_above:
        return max(d for d in av if d < base)

    if int(answered_count) == 0:
        return at_or_above[0]

    # After a miss, streak is 0 — finish never-attempted cards at this band before stepping up.
    if int(streak) == 0 and base in av:
        return base

    soft_cap = min(10, base + 1)
    in_band = [d for d in at_or_above if d <= soft_cap]
    if in_band:
        return max(in_band)
    above = [d for d in at_or_above if d > soft_cap]
    if above:
        return min(above)
    return at_or_above[-1]


def _mark_seen(r: redis.Redis, *, user_id: str, question_id: str) -> None:
    key = seen_zset_key(user_id)
    now_ms = int(time.time() * 1000)
    r.zadd(key, {question_id: now_ms})
    r.expire(key, settings.seen_window_ttl_seconds)

    # Keep bounded size.
    card = r.zcard(key)
    overflow = int(card) - int(settings.seen_window_size)
    if overflow > 0:
        # Remove oldest entries by rank (ascending score).
        r.zremrangebyrank(key, 0, overflow - 1)


def _is_seen(r: redis.Redis, *, user_id: str, question_id: str) -> bool:
    return r.zscore(seen_zset_key(user_id), question_id) is not None


def _refill_buffer_once(
    *,
    user_id: str,
    difficulty: int,
    db: Session,
    r: redis.Redis,
    target_size: int,
    avoid_question_id: Optional[str] = None,
) -> None:
    buf_key = question_buffer_key(user_id)
    lock_key = question_buffer_refill_lock_key(user_id)

    # Fast lock to avoid duplicate refill storms.
    if not r.set(lock_key, "1", nx=True, ex=10):
        return

    try:
        current_len = int(r.llen(buf_key))
        need = max(0, int(target_size) - current_len)
        if need <= 0:
            return

        chosen: list[str] = []
        attempts = 0
        max_attempts = 3
        fetch_n = max(need * 3, need + 5)

        # Try a few rounds to overcome "mostly seen" inventories.
        while len(chosen) < need and attempts < max_attempts:
            attempts += 1
            stmt = (
                select(Question.id)
                .where(
                    Question.difficulty == int(difficulty),
                    _question_never_attempted_by(user_id),
                )
                .order_by(func.random())
                .limit(fetch_n)
            )
            candidates = db.execute(stmt).scalars().all()
            if not candidates:
                stmt_any = (
                    select(Question.id)
                    .where(_question_never_attempted_by(user_id))
                    .order_by(func.random())
                    .limit(fetch_n)
                )
                candidates = db.execute(stmt_any).scalars().all()

            for qid in candidates:
                qid_s = str(qid)
                if qid_s in chosen:
                    continue
                if avoid_question_id and qid_s == avoid_question_id:
                    continue
                if _is_seen(r, user_id=user_id, question_id=qid_s):
                    continue
                chosen.append(qid_s)
                if len(chosen) >= need:
                    break

            fetch_n = min(fetch_n * 2, 500)

        if not chosen:
            stmt = (
                select(Question.id)
                .where(
                    Question.difficulty == int(difficulty),
                    _question_never_attempted_by(user_id),
                )
                .order_by(func.random())
                .limit(need)
            )
            if avoid_question_id and _should_avoid_last_question(
                db, difficulty=int(difficulty), last_question_id=avoid_question_id
            ):
                stmt = stmt.where(Question.id != avoid_question_id)
            candidates = db.execute(stmt).scalars().all()
            chosen = [str(x) for x in candidates[:need]]
            if not chosen and avoid_question_id:
                stmt = (
                    select(Question.id)
                    .where(
                        Question.difficulty == int(difficulty),
                        _question_never_attempted_by(user_id),
                    )
                    .order_by(func.random())
                    .limit(need)
                )
                candidates = db.execute(stmt).scalars().all()
                chosen = [str(x) for x in candidates[:need]]
            if not chosen:
                stmt_any = (
                    select(Question.id)
                    .where(_question_never_attempted_by(user_id))
                    .order_by(func.random())
                    .limit(need)
                )
                candidates = db.execute(stmt_any).scalars().all()
                chosen = [str(x) for x in candidates[:need]]

        if chosen:
            # Append to the right; /next will pop from the right (FIFO).
            r.rpush(buf_key, *chosen)
            r.expire(buf_key, settings.question_buffer_ttl_seconds)
    finally:
        # Let lock expire naturally; no need to delete.
        pass


def _maybe_async_refill(
    *,
    user_id: str,
    difficulty: int,
    r: redis.Redis,
    avoid_question_id: Optional[str] = None,
) -> None:
    # Fire-and-forget best-effort refill.
    def _run() -> None:
        db = SessionLocal()
        try:
            _refill_buffer_once(
                user_id=user_id,
                difficulty=difficulty,
                db=db,
                r=r,
                target_size=int(settings.question_buffer_size),
                avoid_question_id=avoid_question_id,
            )
        except Exception:
            return
        finally:
            db.close()

    t = threading.Thread(target=_run, daemon=True)
    t.start()


def _next_question_response(*, q: Question, state: UserState, session_id: Optional[str]) -> NextQuestionResponse:
    return NextQuestionResponse(
        questionId=q.id,
        difficulty=int(q.difficulty),
        userDifficulty=int(state.current_difficulty),
        prompt=q.prompt,
        choices=list(q.choices),
        sessionId=session_id or "single",
        stateVersion=int(state.state_version),
        currentScore=int(state.total_score),
        currentStreak=int(state.streak),
    )


def _get_locked_user_state_for_next(db: Session, *, user_id: str) -> UserState:
    # Lock here too so concurrent /next calls can't assign different active questions.
    return _get_locked_user_state(db, user_id=user_id)


def _get_or_assign_active_question(
    *,
    user_id: str,
    state: UserState,
    session_id: Optional[str],
    db: Session,
    r: redis.Redis,
) -> Question:
    available_difficulties = _difficulties_with_eligible(db, user_id=user_id)
    if not available_difficulties:
        raise NoEligibleQuestionsError()
    attempted = _attempted_question_ids(db, user_id=user_id)

    # Single active question per user.
    if state.current_question_id:
        q = db.get(Question, state.current_question_id)
        if q:
            if q.id in attempted:
                state.current_question_id = None
            else:
                if int(state.current_difficulty) != int(q.difficulty):
                    state.current_difficulty = int(q.difficulty)
                return q
        else:
            state.current_question_id = None

    buf_key = question_buffer_key(user_id)

    # Pop from buffer but enforce that the served question difficulty matches the current adaptive difficulty.
    # This prevents stale buffer items (from older difficulties) from being served after difficulty changes.
    target_difficulty = _choose_available_difficulty(
        base_difficulty=int(state.current_difficulty),
        streak=int(state.streak),
        answered_count=int(state.answered_count),
        available_difficulties=available_difficulties,
    )
    # Keep state aligned with the actual availability bucket we can serve.
    state.current_difficulty = int(target_difficulty)
    avoid_last_id: Optional[str] = None
    if _should_avoid_last_question(
        db, difficulty=int(target_difficulty), last_question_id=state.last_question_id
    ):
        avoid_last_id = state.last_question_id

    q = None
    max_pops = 24
    for _i in range(max_pops):
        qid = r.rpop(buf_key)
        if qid is None:
            break
        cand = db.get(Question, str(qid))
        if not cand:
            continue
        if cand.id in attempted:
            continue
        if int(cand.difficulty) != target_difficulty:
            # Discard mismatched difficulty item.
            continue
        if avoid_last_id and cand.id == avoid_last_id:
            continue
        # Avoid recently seen questions when possible (best-effort).
        if _is_seen(r, user_id=user_id, question_id=cand.id):
            continue
        q = cand
        break

    if q is None:
        # Ensure buffer has items for the current difficulty.
        _refill_buffer_once(
            user_id=user_id,
            difficulty=target_difficulty,
            db=db,
            r=r,
            target_size=int(settings.question_buffer_size),
            avoid_question_id=avoid_last_id,
        )
        for _i in range(max_pops):
            qid = r.rpop(buf_key)
            if qid is None:
                break
            cand = db.get(Question, str(qid))
            if not cand:
                continue
            if cand.id in attempted:
                continue
            if int(cand.difficulty) != target_difficulty:
                continue
            if avoid_last_id and cand.id == avoid_last_id:
                continue
            if _is_seen(r, user_id=user_id, question_id=cand.id):
                continue
            q = cand
            break

    if q is None:
        # Final fallback: DB pick — serve ``target_difficulty`` first if possible, then widen 10 → 1 among the rest.
        for d in _db_fallback_difficulty_order(target_difficulty, available_difficulties):
            al = (
                avoid_last_id
                if _should_avoid_last_question(db, difficulty=int(d), last_question_id=avoid_last_id)
                else None
            )
            for _i in range(10):
                stmt = (
                    select(Question.id)
                    .where(
                        Question.difficulty == int(d),
                        _question_never_attempted_by(user_id),
                    )
                    .order_by(func.random())
                    .limit(1)
                )
                if al:
                    stmt = stmt.where(Question.id != al)
                qid = db.execute(stmt).scalars().first()
                if qid is None and al:
                    stmt = (
                        select(Question.id)
                        .where(
                            Question.difficulty == int(d),
                            _question_never_attempted_by(user_id),
                        )
                        .order_by(func.random())
                        .limit(1)
                    )
                    qid = db.execute(stmt).scalars().first()
                if qid is None:
                    break
                cand = db.get(Question, str(qid))
                if not cand:
                    continue
                if _is_seen(r, user_id=user_id, question_id=cand.id):
                    continue
                q = cand
                state.current_difficulty = int(d)
                target_difficulty = int(d)
                break
            if q is not None:
                break

        if q is None:
            raise NoEligibleQuestionsError()

    # Low-watermark refill in background.
    try:
        if int(r.llen(buf_key)) < int(settings.question_buffer_low_watermark):
            _maybe_async_refill(
                user_id=user_id,
                difficulty=target_difficulty,
                r=r,
                avoid_question_id=avoid_last_id,
            )
    except Exception:
        pass

    _mark_seen(r, user_id=user_id, question_id=q.id)

    state.current_question_id = q.id
    state.state_version = int(state.state_version) + 1
    return q


def next_question(
    *,
    user_id: str,
    session_id: Optional[str],
    db: Session,
    r: redis.Redis,
) -> NextQuestionResponse:
    # Cache-first read (optional); DB is source of truth.
    _ = get_cached_user_state(r, user_id)

    state = _get_locked_user_state_for_next(db, user_id=user_id)
    decay_streak_if_needed(state)

    q = _get_or_assign_active_question(
        user_id=user_id,
        state=state,
        session_id=session_id,
        db=db,
        r=r,
    )
    db.commit()
    # /next mutates user_state (current_question_id/state_version, and may adjust difficulty),
    # so invalidate derived caches like metrics (cache-aside).
    pipe = r.pipeline(transaction=False)
    set_cached_user_state(pipe, state)  # type: ignore[arg-type]
    pipe.delete(metrics_key(user_id))
    pipe.execute()
    return _next_question_response(q=q, state=state, session_id=session_id)


def _get_locked_user_state(db: Session, *, user_id: str) -> UserState:
    state = (
        db.execute(select(UserState).where(UserState.user_id == user_id).with_for_update())
        .scalars()
        .first()
    )
    if not state:
        state = ensure_user_state(db, user_id)
        db.refresh(state, with_for_update=True)
    return state


def _validate_submit_answer(state: UserState, *, expected_state_version: int, question_id: str) -> None:
    if int(state.state_version) != int(expected_state_version):
        raise StateVersionConflict()
    if state.current_question_id != question_id:
        raise NotCurrentQuestion()


@dataclass(frozen=True)
class _AnswerOutcome:
    correct: bool
    score_delta: int
    streak_after: int
    max_streak_after: int
    new_difficulty: int
    answered_count: int
    correct_count: int
    ema_accuracy: float
    streak_at_answer_for_log: int
    state_version_for_log: int


def _compute_answer_outcome(
    *,
    db: Session,
    user_id: str,
    state: UserState,
    question: Question,
    answer: str,
) -> _AnswerOutcome:
    decay_streak_if_needed(state)
    correct = sha256(answer) == question.correct_answer_hash
    streak_after = int(state.streak) + 1 if correct else 0
    max_streak_after = max(int(state.max_streak), streak_after)
    if correct:
        new_diff = next_difficulty_on_correct(current=int(question.difficulty))
    else:
        new_diff = _difficulty_after_wrong(
            db,
            user_id=user_id,
            user_level=int(state.current_difficulty),
            question=question,
        )
    score_delta = score_delta_for_answer(
        difficulty=int(question.difficulty),
        correct=correct,
        streak_after=streak_after,
    )
    answered_count = int(state.answered_count) + 1
    correct_count = int(state.correct_count) + (1 if correct else 0)
    ema = float(state.ema_accuracy)
    ema = (settings.ema_alpha * (1.0 if correct else 0.0)) + ((1.0 - settings.ema_alpha) * ema)
    new_sv = int(state.state_version) + 1
    return _AnswerOutcome(
        correct=bool(correct),
        score_delta=int(score_delta),
        streak_after=streak_after,
        max_streak_after=max_streak_after,
        new_difficulty=int(new_diff),
        answered_count=answered_count,
        correct_count=correct_count,
        ema_accuracy=ema,
        streak_at_answer_for_log=streak_after,
        state_version_for_log=new_sv,
    )


def _apply_answer_outcome(state: UserState, question: Question, outcome: _AnswerOutcome) -> None:
    state.streak = outcome.streak_after
    state.max_streak = outcome.max_streak_after
    state.current_difficulty = outcome.new_difficulty
    state.total_score = int(state.total_score) + int(outcome.score_delta)
    state.last_question_id = question.id
    state.last_answer_at = utcnow()
    state.answered_count = outcome.answered_count
    state.correct_count = outcome.correct_count
    state.ema_accuracy = outcome.ema_accuracy
    state.current_question_id = None
    state.state_version = outcome.state_version_for_log


def _try_reserve_answer_log_row(db: Session, *, body: SubmitAnswerRequest, question: Question, outcome: _AnswerOutcome) -> bool:
    """Insert the one allowed row per (user, question). Returns False if already answered this question."""
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as dialect_insert
    else:
        from sqlalchemy.dialects.sqlite import insert as dialect_insert

    stmt = (
        dialect_insert(AnswerLog)
        .values(
            id=str(uuid.uuid4()),
            user_id=body.userId,
            question_id=question.id,
            difficulty=int(question.difficulty),
            answer=body.answer,
            correct=bool(outcome.correct),
            score_delta=int(outcome.score_delta),
            streak_at_answer=int(outcome.streak_at_answer_for_log),
            state_version=int(outcome.state_version_for_log),
            answer_idempotency_key=body.answerIdempotencyKey,
        )
        .on_conflict_do_nothing(index_elements=["user_id", "question_id"])
        .returning(AnswerLog.id)
    )
    inserted = db.execute(stmt).first()
    return inserted is not None


def _response_from_current_state(
    *,
    correct: bool,
    score_delta: int,
    state: UserState,
    r: redis.Redis,
) -> SubmitAnswerResponse:
    rank_score = r.zrevrank(lb_score_key(), state.user_id)
    rank_streak = r.zrevrank(lb_streak_key(), state.user_id)
    return SubmitAnswerResponse(
        correct=bool(correct),
        newDifficulty=int(state.current_difficulty),
        newStreak=int(state.streak),
        scoreDelta=int(score_delta),
        totalScore=int(state.total_score),
        stateVersion=int(state.state_version),
        leaderboardRankScore=(int(rank_score) + 1) if rank_score is not None else None,
        leaderboardRankStreak=(int(rank_streak) + 1) if rank_streak is not None else None,
    )


def _post_answer_redis_updates(
    *,
    r: redis.Redis,
    state: UserState,
) -> None:
    pipe = r.pipeline(transaction=False)
    set_cached_user_state(pipe, state)  # type: ignore[arg-type]
    pipe.zadd(lb_score_key(), {state.user_id: int(state.total_score)})
    pipe.zadd(lb_streak_key(), {state.user_id: int(state.streak)})
    pipe.delete(metrics_key(state.user_id))
    pipe.delete(question_buffer_key(state.user_id))
    pipe.execute()


def _build_leaderboard_update_payload(
    *,
    user_id: str,
    total_score: int,
    streak: int,
    current_difficulty: int,
    r: redis.Redis,
) -> dict:
    rank_score = r.zrevrank(lb_score_key(), user_id)
    rank_streak = r.zrevrank(lb_streak_key(), user_id)
    top_n = max(1, int(settings.ws_leaderboard_top_n))
    top_score_items = r.zrevrange(lb_score_key(), 0, top_n - 1, withscores=True)
    top_streak_items = r.zrevrange(lb_streak_key(), 0, top_n - 1, withscores=True)
    return {
        "type": "leaderboard_update",
        "changedUser": {
            "userId": user_id,
            "totalScore": int(total_score),
            "streak": int(streak),
            "currentDifficulty": int(current_difficulty),
            "rankScore": (int(rank_score) + 1) if rank_score is not None else None,
            "rankStreak": (int(rank_streak) + 1) if rank_streak is not None else None,
        },
        "topScore": [{"userId": str(uid), "score": int(score)} for uid, score in top_score_items],
        "topStreak": [{"userId": str(uid), "score": int(score)} for uid, score in top_streak_items],
    }


def submit_answer(
    *,
    body: SubmitAnswerRequest,
    db: Session,
    r: redis.Redis,
) -> SubmitAnswerResult:
    idem_k = idem_key(body.userId, body.answerIdempotencyKey)
    cached_resp = r.get(idem_k)
    if cached_resp:
        # No emit on cached response.
        return SubmitAnswerResult(
            response=SubmitAnswerResponse.model_validate_json(cached_resp),
            emitted_payload=None,
        )

    q = db.get(Question, body.questionId)
    if not q:
        raise QuestionNotFound()

    state = _get_locked_user_state(db, user_id=body.userId)
    _validate_submit_answer(state, expected_state_version=int(body.stateVersion), question_id=body.questionId)
    outcome = _compute_answer_outcome(db=db, user_id=body.userId, state=state, question=q, answer=body.answer)
    if not _try_reserve_answer_log_row(db, body=body, question=q, outcome=outcome):
        db.rollback()
        db.refresh(state)
        raise QuestionAlreadyMastered()
    _apply_answer_outcome(state, q, outcome)

    db.commit()

    _post_answer_redis_updates(r=r, state=state)

    _avoid = (
        state.last_question_id
        if _should_avoid_last_question(
            db, difficulty=int(state.current_difficulty), last_question_id=state.last_question_id
        )
        else None
    )
    _refill_buffer_once(
        user_id=body.userId,
        difficulty=int(state.current_difficulty),
        db=db,
        r=r,
        target_size=int(settings.question_buffer_size),
        avoid_question_id=_avoid,
    )

    resp = _response_from_current_state(
        correct=outcome.correct, score_delta=outcome.score_delta, state=state, r=r
    )
    r.set(idem_k, resp.model_dump_json(), ex=settings.idempotency_ttl_seconds)

    # Realtime leaderboard payload strategy:
    # - Simplest MVP (what we do here): always broadcast updated top-N after every answer.
    # - Optimized: track old/new ranks and only broadcast when top-N could change
    #   (e.g., user crosses the N boundary or their score changes relative to top-N).
    return SubmitAnswerResult(
        response=resp,
        emitted_payload=_build_leaderboard_update_payload(
            user_id=body.userId,
            total_score=int(state.total_score),
            streak=int(state.streak),
            current_difficulty=int(state.current_difficulty),
            r=r,
        ),
    )


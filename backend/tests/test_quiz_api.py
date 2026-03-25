from __future__ import annotations

import time
import uuid

import pytest

from app.db.models import AnswerLog, UserState


def test_next_returns_single_active_question(client):
    r1 = client.get("/v1/quiz/next", params={"userId": "u-test", "sessionId": "single"})
    assert r1.status_code == 200
    body1 = r1.json()
    assert body1["questionId"]
    assert body1["stateVersion"] >= 1

    # Calling /next again should return the same active question.
    r2 = client.get("/v1/quiz/next", params={"userId": "u-test", "sessionId": "single"})
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2["questionId"] == body1["questionId"]
    assert body2["stateVersion"] == body1["stateVersion"]


def test_answer_correct_updates_score_streak_and_leaderboards(client):
    nxt = client.get("/v1/quiz/next", params={"userId": "u-a", "sessionId": "single"}).json()
    qid = nxt["questionId"]
    sv = nxt["stateVersion"]

    # We seeded q-1 correct=4, q-1b correct=6, q-2 correct=Queue, q-3 correct=O(log n)
    answer_map = {"q-1": "4", "q-1b": "6", "q-2": "Queue", "q-3": "O(log n)"}
    ans = answer_map[qid]

    idem = f"t-{time.time_ns()}"
    resp = client.post(
        "/v1/quiz/answer",
        json={
            "userId": "u-a",
            "sessionId": "single",
            "questionId": qid,
            "answer": ans,
            "stateVersion": sv,
            "answerIdempotencyKey": idem,
        },
    )
    assert resp.status_code == 200
    b = resp.json()
    assert b["correct"] is True
    assert b["totalScore"] > 0
    assert b["newStreak"] == 1
    assert b["leaderboardRankScore"] == 1

    lb = client.get("/v1/leaderboard/score", params={"userId": "u-a", "n": 10}).json()
    assert lb["yourRank"] == 1
    assert lb["yourScore"] == b["totalScore"]


def test_answer_idempotency_does_not_double_apply(client):
    nxt = client.get("/v1/quiz/next", params={"userId": "u-idem", "sessionId": "single"}).json()
    qid = nxt["questionId"]
    sv = nxt["stateVersion"]

    answer_map = {"q-1": "4", "q-1b": "6", "q-2": "Queue", "q-3": "O(log n)"}
    ans = answer_map[qid]
    idem = f"idem-{time.time_ns()}"

    r1 = client.post(
        "/v1/quiz/answer",
        json={
            "userId": "u-idem",
            "sessionId": "single",
            "questionId": qid,
            "answer": ans,
            "stateVersion": sv,
            "answerIdempotencyKey": idem,
        },
    )
    assert r1.status_code == 200
    b1 = r1.json()

    # Replay exact same request (same idempotency key + stateVersion).
    r2 = client.post(
        "/v1/quiz/answer",
        json={
            "userId": "u-idem",
            "sessionId": "single",
            "questionId": qid,
            "answer": ans,
            "stateVersion": sv,
            "answerIdempotencyKey": idem,
        },
    )
    assert r2.status_code == 200
    b2 = r2.json()

    assert b2["totalScore"] == b1["totalScore"]
    assert b2["stateVersion"] == b1["stateVersion"]


def test_metrics_endpoint_works(client):
    # Ensure user exists and has some activity.
    nxt = client.get("/v1/quiz/next", params={"userId": "u-m", "sessionId": "single"}).json()
    qid = nxt["questionId"]
    sv = nxt["stateVersion"]
    answer_map = {"q-1": "4", "q-1b": "6", "q-2": "Queue", "q-3": "O(log n)"}
    ans = answer_map[qid]

    client.post(
        "/v1/quiz/answer",
        json={
            "userId": "u-m",
            "sessionId": "single",
            "questionId": qid,
            "answer": ans,
            "stateVersion": sv,
            "answerIdempotencyKey": f"m-{time.time_ns()}",
        },
    )

    m = client.get("/v1/quiz/metrics", params={"userId": "u-m"})
    assert m.status_code == 200
    body = m.json()
    assert "totalScore" in body
    assert "accuracy" in body
    assert isinstance(body["recentPerformance"], list)


def test_healthz_ok(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_answer_wrong_applies_penalty_and_resets_streak(client):
    nxt = client.get("/v1/quiz/next", params={"userId": "u-wrong", "sessionId": "single"}).json()
    r = client.post(
        "/v1/quiz/answer",
        json={
            "userId": "u-wrong",
            "sessionId": "single",
            "questionId": nxt["questionId"],
            "answer": "definitely-not-the-answer",
            "stateVersion": nxt["stateVersion"],
            "answerIdempotencyKey": f"w-{time.time_ns()}",
        },
    )
    assert r.status_code == 200
    b = r.json()
    assert b["correct"] is False
    assert b["newStreak"] == 0
    assert b["scoreDelta"] < 0
    assert b["totalScore"] < 0


def test_state_version_conflict_returns_409(client):
    nxt = client.get("/v1/quiz/next", params={"userId": "u-409-sv", "sessionId": "single"}).json()
    r = client.post(
        "/v1/quiz/answer",
        json={
            "userId": "u-409-sv",
            "sessionId": "single",
            "questionId": nxt["questionId"],
            "answer": "4",
            "stateVersion": nxt["stateVersion"] + 99,
            "answerIdempotencyKey": f"sv-{time.time_ns()}",
        },
    )
    assert r.status_code == 409
    assert r.json()["detail"] == "state_version_conflict"


def test_not_current_question_returns_409(client):
    nxt = client.get("/v1/quiz/next", params={"userId": "u-409-q", "sessionId": "single"}).json()
    other_id = "q-3" if nxt["questionId"] != "q-3" else "q-2"
    r = client.post(
        "/v1/quiz/answer",
        json={
            "userId": "u-409-q",
            "sessionId": "single",
            "questionId": other_id,
            "answer": "4",
            "stateVersion": nxt["stateVersion"],
            "answerIdempotencyKey": f"q-{time.time_ns()}",
        },
    )
    assert r.status_code == 409
    assert r.json()["detail"] == "not_current_question"


def test_question_not_found_returns_404(client):
    nxt = client.get("/v1/quiz/next", params={"userId": "u-404", "sessionId": "single"}).json()
    r = client.post(
        "/v1/quiz/answer",
        json={
            "userId": "u-404",
            "sessionId": "single",
            "questionId": "does-not-exist",
            "answer": "x",
            "stateVersion": nxt["stateVersion"],
            "answerIdempotencyKey": f"n-{time.time_ns()}",
        },
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "question_not_found"


def test_metrics_unknown_user_returns_404(client):
    r = client.get("/v1/quiz/metrics", params={"userId": "unknown-user-never-seen"})
    assert r.status_code == 404
    assert r.json()["detail"] == "user_not_found"


def test_leaderboard_streak_endpoint_returns_streak_rank(client):
    nxt = client.get("/v1/quiz/next", params={"userId": "u-streak-lb", "sessionId": "single"}).json()
    answer_map = {"q-1": "4", "q-2": "Queue", "q-3": "O(log n)", "q-1b": "6"}
    ans = answer_map[nxt["questionId"]]
    client.post(
        "/v1/quiz/answer",
        json={
            "userId": "u-streak-lb",
            "sessionId": "single",
            "questionId": nxt["questionId"],
            "answer": ans,
            "stateVersion": nxt["stateVersion"],
            "answerIdempotencyKey": f"lb-{time.time_ns()}",
        },
    )
    lb = client.get("/v1/leaderboard/streak", params={"userId": "u-streak-lb", "n": 10}).json()
    assert lb["yourRank"] == 1
    assert lb["yourScore"] == 1


def test_next_after_correct_serves_new_card_and_higher_difficulty(client):
    nxt1 = client.get("/v1/quiz/next", params={"userId": "u-step", "sessionId": "single"}).json()
    assert nxt1["difficulty"] == 1
    q1 = nxt1["questionId"]
    client.post(
        "/v1/quiz/answer",
        json={
            "userId": "u-step",
            "sessionId": "single",
            "questionId": q1,
            "answer": "4" if q1 == "q-1" else "6",
            "stateVersion": nxt1["stateVersion"],
            "answerIdempotencyKey": f"st-{time.time_ns()}",
        },
    )
    nxt2 = client.get("/v1/quiz/next", params={"userId": "u-step", "sessionId": "single"}).json()
    assert nxt2["questionId"] != q1
    # With "climb when possible", the next card may jump to the hardest band >= user level (e.g. 3 not 2).
    assert nxt2["difficulty"] >= 2


def test_metrics_accuracy_reflects_correct_and_wrong(client):
    uid = "u-acc"
    nxt = client.get("/v1/quiz/next", params={"userId": uid, "sessionId": "single"}).json()
    client.post(
        "/v1/quiz/answer",
        json={
            "userId": uid,
            "sessionId": "single",
            "questionId": nxt["questionId"],
            "answer": "4" if nxt["questionId"] == "q-1" else "6",
            "stateVersion": nxt["stateVersion"],
            "answerIdempotencyKey": f"a1-{time.time_ns()}",
        },
    )
    nxt2 = client.get("/v1/quiz/next", params={"userId": uid, "sessionId": "single"}).json()
    client.post(
        "/v1/quiz/answer",
        json={
            "userId": uid,
            "sessionId": "single",
            "questionId": nxt2["questionId"],
            "answer": "wrong",
            "stateVersion": nxt2["stateVersion"],
            "answerIdempotencyKey": f"a2-{time.time_ns()}",
        },
    )
    m = client.get("/v1/quiz/metrics", params={"userId": uid}).json()
    assert abs(m["accuracy"] - 0.5) < 1e-9


def test_wrong_answer_steps_down_from_user_level_not_card_level(client, db_session):
    """A miss must not raise adaptive difficulty because the card was harder than user_level."""
    uid = "u-wrong-user-level"
    client.get("/v1/quiz/next", params={"userId": uid, "sessionId": "single"})
    st = db_session.get(UserState, uid)
    assert st is not None
    st.current_difficulty = 2
    st.current_question_id = "q-3"
    st.state_version = 11
    db_session.commit()

    r = client.post(
        "/v1/quiz/answer",
        json={
            "userId": uid,
            "sessionId": "single",
            "questionId": "q-3",
            "answer": "nope",
            "stateVersion": 11,
            "answerIdempotencyKey": f"wl-{time.time_ns()}",
        },
    )
    assert r.status_code == 200
    # Card is difficulty 3; naive (card - 1) would be 2 — we step from user level 2 → 1 with inventory check.
    assert r.json()["newDifficulty"] == 1


def test_after_wrong_at_difficulty_one_next_prefers_other_question(client):
    uid = "u-avoid-dup"
    nxt = client.get("/v1/quiz/next", params={"userId": uid, "sessionId": "single"}).json()
    cur = nxt["questionId"]
    assert cur in ("q-1", "q-1b")
    other = "q-1b" if cur == "q-1" else "q-1"
    client.post(
        "/v1/quiz/answer",
        json={
            "userId": uid,
            "sessionId": "single",
            "questionId": cur,
            "answer": "not-right",
            "stateVersion": nxt["stateVersion"],
            "answerIdempotencyKey": f"wrong-{time.time_ns()}",
        },
    )
    nxt2 = client.get("/v1/quiz/next", params={"userId": uid, "sessionId": "single"}).json()
    assert nxt2["questionId"] == other
    assert nxt2["difficulty"] == 1


def test_next_never_serves_mastered_question_again(client):
    uid = "u-skip-mastered"
    nxt = client.get("/v1/quiz/next", params={"userId": uid, "sessionId": "single"}).json()
    first = nxt["questionId"]
    ans = {"q-1": "4", "q-1b": "6", "q-2": "Queue", "q-3": "O(log n)"}[first]
    client.post(
        "/v1/quiz/answer",
        json={
            "userId": uid,
            "sessionId": "single",
            "questionId": first,
            "answer": ans,
            "stateVersion": nxt["stateVersion"],
            "answerIdempotencyKey": f"ok-{time.time_ns()}",
        },
    )
    nxt2 = client.get("/v1/quiz/next", params={"userId": uid, "sessionId": "single"}).json()
    assert nxt2["questionId"] != first


def test_next_returns_404_when_all_questions_mastered(client):
    uid = "u-all-done"
    for _ in range(6):
        nxt = client.get("/v1/quiz/next", params={"userId": uid, "sessionId": "single"})
        if nxt.status_code == 404:
            assert nxt.json()["detail"] == "no_eligible_questions"
            return
        body = nxt.json()
        qid = body["questionId"]
        ans = {"q-1": "4", "q-1b": "6", "q-2": "Queue", "q-3": "O(log n)"}[qid]
        r = client.post(
            "/v1/quiz/answer",
            json={
                "userId": uid,
                "sessionId": "single",
                "questionId": qid,
                "answer": ans,
                "stateVersion": body["stateVersion"],
                "answerIdempotencyKey": f"x-{time.time_ns()}",
            },
        )
        assert r.status_code == 200
    pytest.fail("expected 404 no_eligible_questions before loop exhausted")


def test_cannot_earn_correct_true_again_on_mastered_question(client, db_session):
    uid = "u-mastered"
    client.get("/v1/quiz/next", params={"userId": uid, "sessionId": "single"})
    db_session.add(
        AnswerLog(
            id=str(uuid.uuid4()),
            user_id=uid,
            question_id="q-1",
            difficulty=1,
            answer="4",
            correct=True,
            score_delta=0,
            streak_at_answer=0,
            state_version=0,
            answer_idempotency_key="seed-prior-answer",
        )
    )
    st = db_session.get(UserState, uid)
    assert st is not None
    st.current_question_id = "q-1"
    st.state_version = 42
    db_session.commit()

    r = client.post(
        "/v1/quiz/answer",
        json={
            "userId": uid,
            "sessionId": "single",
            "questionId": "q-1",
            "answer": "4",
            "stateVersion": 42,
            "answerIdempotencyKey": f"replay-{time.time_ns()}",
        },
    )
    assert r.status_code == 409
    assert r.json()["detail"] == "question_already_mastered"


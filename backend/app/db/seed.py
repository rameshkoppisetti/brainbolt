import hashlib
import json
from pathlib import Path

from sqlalchemy import select

from app.db.engine import SessionLocal
from app.db.models import Question, User, UserState


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def load_questions():
    p = Path(__file__).resolve().parents[1] / "data" / "questions.seed.json"
    return json.loads(p.read_text(encoding="utf-8"))


def main() -> None:
    seed_users = ["u-alice", "u-bob", "u-carol", "u-dave"]
    questions = load_questions()

    db = SessionLocal()
    try:
        # Users + state
        for uid in seed_users:
            if not db.get(User, uid):
                db.add(User(id=uid))
                db.flush()
            if not db.get(UserState, uid):
                db.add(UserState(user_id=uid, current_difficulty=1, ema_accuracy=0.0))

        # Questions
        existing = set(db.execute(select(Question.id)).scalars().all())
        for q in questions:
            if q["id"] in existing:
                # Keep it simple: no update path for seed (fine for demo)
                continue
            db.add(
                Question(
                    id=q["id"],
                    difficulty=int(q["difficulty"]),
                    prompt=q["prompt"],
                    choices=q["choices"],
                    correct_answer_hash=sha256(q["correctAnswer"]),
                    tags=q.get("tags", []),
                )
            )

        db.commit()
        print("Seed complete")
    finally:
        db.close()


if __name__ == "__main__":
    main()


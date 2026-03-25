from sqlalchemy import text

from app.db.base import Base
from app.db.engine import engine
from app.db import models  # noqa: F401


def main() -> None:
    if engine.dialect.name == "postgresql":
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))

    Base.metadata.create_all(bind=engine)

    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS user_question_mastery"))

    print("Migration complete")


if __name__ == "__main__":
    main()

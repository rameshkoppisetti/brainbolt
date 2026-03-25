import os


class Settings:
    port: int = int(os.getenv("PORT", "8080"))
    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql+psycopg://brainbolt:brainbolt@localhost:5432/brainbolt"
    )
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    streak_decay_seconds: int = int(os.getenv("STREAK_DECAY_SECONDS", "900"))
    ema_alpha: float = float(os.getenv("EMA_ALPHA", "0.2"))
    max_streak_multiplier: float = float(os.getenv("MAX_STREAK_MULTIPLIER", "3"))
    cors_origin: str = os.getenv("CORS_ORIGIN", "*")
    idempotency_ttl_seconds: int = int(os.getenv("IDEMPOTENCY_TTL_SECONDS", str(60 * 60 * 24)))
    metrics_cache_ttl_seconds: int = int(os.getenv("METRICS_CACHE_TTL_SECONDS", "15"))
    question_buffer_size: int = int(os.getenv("QUESTION_BUFFER_SIZE", "20"))
    question_buffer_low_watermark: int = int(os.getenv("QUESTION_BUFFER_LOW_WATERMARK", "2"))
    question_buffer_ttl_seconds: int = int(os.getenv("QUESTION_BUFFER_TTL_SECONDS", str(60 * 30)))
    seen_window_size: int = int(os.getenv("SEEN_WINDOW_SIZE", "100"))
    seen_window_ttl_seconds: int = int(os.getenv("SEEN_WINDOW_TTL_SECONDS", str(60 * 60 * 24)))
    ws_leaderboard_top_n: int = int(os.getenv("WS_LEADERBOARD_TOP_N", "10"))
    wrong_penalty_per_difficulty: int = int(os.getenv("WRONG_PENALTY_PER_DIFFICULTY", "5"))


settings = Settings()


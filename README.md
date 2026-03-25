## BrainBolt — Adaptive Infinite Quiz Platform
<img width="1399" height="892" alt="image" src="https://github.com/user-attachments/assets/8f4b57a0-2131-450c-8671-d259aaf8442e" />

BrainBolt is a real-time adaptive quiz system that serves one question at a time and dynamically adjusts difficulty based on user performance. It includes streak-based scoring, idempotent answer handling, and live leaderboards.

---

## 🚀 Features

- 🎯 Adaptive difficulty (based on streak + correctness)
- 🔁 Infinite quiz (one question at a time)
- ⚡ Real-time leaderboard updates (WebSocket)
- 🧠 Streak-based scoring system
- 🔒 Strong per-user consistency
- ♻️ Idempotent answer submission
- 🚀 Low-latency question delivery using Redis buffer

---

## 🏗️ Architecture

```text
Client
  |
API Gateway / Load Balancer
  |
  +-------------------+------------------+
  |                   |                  |
Quiz Service      Leaderboard API   WebSocket Manager
  |                   |                  |
  |                   |                  |
  +--------- Redis ----+-----------------+
  |      - user_state cache
  |      - idempotency keys
  |      - question buffer
  |      - seen questions
  |      - ZSET lb:score
  |      - ZSET lb:streak
  |
Postgres
  - users
  - questions
  - user_state
  - answer_log


This project is being built **backend-first** using:
- **FastAPI**
- **SQLAlchemy**
- **Postgres**
- **Redis**
- **Socket.IO** (python-socketio)
- **Docker Compose**

### Folder layout

- `backend/`: **the active implementation**

### Run (local)

```bash
docker compose up --build
```

API will be on `http://localhost:8080`.

### Frontend (React)

In a new terminal:

```bash
npm install
npm run dev
```

Open `http://localhost:5173`.

### MVP endpoints

- `GET /healthz`
- `GET /v1/quiz/next?userId=...`
- `POST /v1/quiz/answer`
- `GET /v1/quiz/metrics?userId=...`
- `GET /v1/leaderboard/score?userId=...`
- `GET /v1/leaderboard/streak?userId=...`

### WebSocket (Socket.IO)

The backend also exposes Socket.IO on the same port. On each answer submission it broadcasts:

- event: `leaderboard:update`
- payload: `{ type: "leaderboard_update", changedUser: {...}, topScore: [...], topStreak: [...] }`

### Run API tests (no Docker)

```bash
cd backend
python3 -m pip install -r requirements.txt -r requirements-dev.txt
pytest -q
```


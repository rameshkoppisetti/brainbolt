## BrainBolt (backend-first)

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


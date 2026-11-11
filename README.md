# Nurses — Oral Exam Trainer Mini App

Telegram Mini App for voice practice of oral qualification exams with AI grading.
See [ARCHITECTURE.md](ARCHITECTURE.md) for the full design.

| Folder | What |
|---|---|
| `backend/` | FastAPI API, SQLAlchemy models, provider adapters, workers |
| `bot/` | aiogram bot (start, contact sharing, payment alerts) |
| `miniapp/` | React + TS + Vite learner app |
| `admin/` | React + TS admin panel |
| `infra/` | docker-compose (Postgres, Redis, MinIO, services) |

## Quick start

```bash
cp .env.example .env   # fill BOT_TOKEN and ADMIN_TELEGRAM_IDS
docker compose -f infra/docker-compose.yml --env-file .env up --build
```

API: http://localhost:8000/health · Mini App: http://localhost:5173 · Admin: http://localhost:5174

Status: scaffold only. Provider adapters are stubs; endpoints beyond auth/courses/health are not implemented yet.

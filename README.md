# Nurses — Oral Exam Trainer Mini App

Telegram Mini App for voice practice of oral qualification exams. Users answer out loud, then grade
themselves against the model answer's key points (or, optionally, Google Gemini grades the recording).
Access is paid by card transfer and approved by hand. See [ARCHITECTURE.md](ARCHITECTURE.md) and
[docs/DEPLOY.md](docs/DEPLOY.md).

| Folder | What |
|---|---|
| `backend/` | FastAPI API, Telegram bot webhook, grading, subscriptions |
| `miniapp/` | React + TS + Vite learner app (runs inside Telegram) |
| `admin/` | React + TS admin panel (runs in a browser, Telegram Login) |
| `infra/` | docker-compose for running everything on one server |

## What works
- **Learner (Mini App):** course and question list with topics, free demo questions, voice recording
  (up to 3 min), self-check or AI grading, results history, profile with language (uz/ru/en),
  paywall with card details and receipt upload, payment status.
- **Admin:** dashboard, payment requests (receipt, approve/reject with reason), users (grant/extend
  access, cancel, block), courses and topics, questions with key points and audio, Excel
  import/export, plans, answer review with teacher score, settings, audit log.
- **Bot:** /start with phone sharing and "Open app", payment alerts to admins with Approve/Reject
  buttons, approval/rejection messages, reminders 3 days and 1 day before expiry.

## Run locally

```bash
cp .env.example .env   # fill BOT_TOKEN and ADMIN_TELEGRAM_IDS
docker compose -f infra/docker-compose.yml --env-file .env up --build
```

API: http://localhost:8000/health · Mini App: http://localhost:5173 · Admin: http://localhost:5174

Tests: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://user@localhost:5432/test pytest`
(API tests need an empty PostgreSQL database; unit tests run without one).

## Not built yet (after MVP)
Mock exam, learn/test modes, statistics charts, favourites, broadcasts, reports, promo codes,
Click/Payme auto-payments, more admin roles, AI voice generation (TTS) in the admin panel.

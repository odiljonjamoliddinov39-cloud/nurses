# Deploy: Railway (backend + bot) and Vercel (miniapp + admin)

The Telegram bot runs inside the backend (webhook at `/telegram/webhook`), so Railway needs only
**Postgres** and **backend**. Uploaded audio and receipts are stored in Postgres. Redis, S3 and the
arq worker are not needed.

## 1. Railway
1. New Project -> Deploy PostgreSQL.
2. New -> GitHub Repo -> `nurses`. Service **backend**: Settings -> Root Directory `backend` (Dockerfile is detected).
   Variables:
   - `DATABASE_URL` = reference the Postgres service's `DATABASE_URL`
   - `BOT_TOKEN` = token from @BotFather
   - `ADMIN_TELEGRAM_IDS` = your Telegram ID(s), comma-separated (from @userinfobot)
   - `CORS_ORIGINS` = your two Vercel URLs, comma-separated
   - `PORT` = `8000` if the public domain targets port 8000
   Then Settings -> Networking -> Generate Domain. Check `https://<domain>/ready`.
   On startup the backend registers the bot webhook on its Railway domain and, once the Mini App URL
   is set (admin Settings), the bot's menu button.

Tables are created on startup; new columns are added by the small `MIGRATIONS` list in `app/main.py`.

## 2. Vercel (two projects, same repo)
- **miniapp**: Root Directory `miniapp`, framework Vite, env `VITE_API_URL=https://<backend domain>`.
- **admin**: Root Directory `admin`, framework Vite, env `VITE_API_URL=https://<backend domain>` and
  `VITE_BOT_USERNAME=<bot username without @>` (for the browser sign-in button).
- Settings -> Environments -> Production: track the branch you push to, so pushes go live.

## 3. Telegram and first run
- BotFather `/setdomain`: pick the bot, enter the admin domain (e.g. `admin-xxxx.vercel.app`).
  The admin panel signs in with Telegram Login; only IDs in `ADMIN_TELEGRAM_IDS` get in.
- Admin panel -> Settings: Mini App URL (the miniapp's production `https://<project>.vercel.app`, not a
  per-deployment URL, which sits behind Vercel's login), card number and holder, free questions.
- Admin panel -> Courses & questions: create a course, tick Published, add or import questions.
- Admin panel -> Plans: add at least one plan.
- Keep `BOT_TOKEN` secret: only in Railway variables, never in git or chat.

## Grading
Default is self-check: after recording, the user sees the model answer and ticks the key points they
covered; the score is the weighted share, 0-5. Every recording is kept, and the admin can set a teacher
score under Answers. For AI grading, choose "AI grading" in Settings and add a Google Gemini API key.

## Moving off Railway later
Everything is plain Docker plus env vars from `.env.example`; `infra/docker-compose.yml` runs the same stack on a VPS.

# Deploy: Railway (backend + bot) and Vercel (miniapp + admin)

Railway runs three things from this repo: **Postgres**, **backend**, **bot**.
Redis and the arq worker are not needed yet (the worker only has a ping task).

## 1. Railway
1. New Project -> Deploy PostgreSQL.
2. New -> GitHub Repo -> `nurses`. Service **backend**: Settings -> Root Directory `backend` (Dockerfile is detected).
   Variables:
   - `DATABASE_URL` = reference the Postgres service's `DATABASE_URL`
   - `BOT_TOKEN` = token from @BotFather
   - `ADMIN_TELEGRAM_IDS` = your Telegram ID(s), comma-separated
   - `CORS_ORIGINS` = your two Vercel URLs, comma-separated (set after step 2)
   Then Settings -> Networking -> Generate Domain. Check `https://<domain>/ready`.
3. New -> GitHub Repo -> `nurses` again. Service **bot**: Root Directory `bot`.
   Variables: `BOT_TOKEN` (same), `MINIAPP_URL` = miniapp Vercel URL (https).

Tables are created on backend startup (Alembic is a TODO).

## 2. Vercel (two projects, same repo)
- **miniapp**: Root Directory `miniapp`, framework Vite, env `VITE_API_URL=https://<backend domain>`.
- **admin**: Root Directory `admin`, framework Vite, env `VITE_API_URL=https://<backend domain>`.

## 3. Telegram
- Set the bot's menu button / Mini App URL (BotFather: `/setmenubutton`) to the miniapp Vercel URL.
- Keep `BOT_TOKEN` secret: only in Railway variables, never in git or chat.

## Moving off Railway later
Everything is plain Docker plus env vars from `.env.example`; `infra/docker-compose.yml` runs the same stack on a VPS.

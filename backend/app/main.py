import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import timedelta

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text

from . import models  # noqa: F401  (register tables)
from . import telegram
from .api import admin, health, learner
from .config import get_settings
from .db import Base, SessionLocal, engine
from .models import Subscription, SubscriptionStatus, User
from .services import get_setting, now_utc, sync_user_status

log = logging.getLogger("uvicorn.error")

# create_all only adds missing tables; columns added to existing tables are listed here.
MIGRATIONS = [
    "ALTER TABLE subscriptions ADD COLUMN IF NOT EXISTS reminded_days INTEGER",
]


async def configure_bot() -> None:
    """Point the bot's webhook at this API and its menu button at the Mini App."""
    settings = get_settings()
    async with SessionLocal() as session:
        miniapp_url = (await get_setting(session, "miniapp_url")) or settings.miniapp_url
    await telegram.setup_bot(settings.public_base, miniapp_url)


async def subscription_job() -> None:
    """Expire ended subscriptions and send reminders 3 days and 1 day before the end."""
    now = now_utc()
    async with SessionLocal() as session:
        ended = (await session.execute(select(Subscription).where(
            Subscription.status == SubscriptionStatus.active, Subscription.ends_at <= now))).scalars().all()
        for sub in ended:
            sub.status = SubscriptionStatus.expired
            user = await session.get(User, sub.user_id)
            if user:
                await session.flush()
                await sync_user_status(session, user)
                from .services import active_subscription
                if not await active_subscription(session, user.id):
                    await telegram.send(user.telegram_id, telegram.tr("expired", user.ui_language))
        soon = (await session.execute(select(Subscription).where(
            Subscription.status == SubscriptionStatus.active, Subscription.ends_at > now,
            Subscription.ends_at <= now + timedelta(days=3)))).scalars().all()
        for sub in soon:
            days_left = 1 if sub.ends_at - now <= timedelta(days=1) else 3
            if sub.reminded_days is not None and sub.reminded_days <= days_left:
                continue
            later = (await session.execute(select(Subscription.id).where(
                Subscription.user_id == sub.user_id, Subscription.status == SubscriptionStatus.active,
                Subscription.ends_at > sub.ends_at))).first()
            sub.reminded_days = days_left
            if later:  # already renewed
                continue
            user = await session.get(User, sub.user_id)
            if user:
                await telegram.send(user.telegram_id, telegram.tr(
                    "remind", user.ui_language, days=days_left, date=sub.ends_at.strftime("%d.%m.%Y")))
        await session.commit()


async def scheduler() -> None:
    while True:
        try:
            await subscription_job()
        except Exception:
            log.exception("subscription job failed")
        await asyncio.sleep(30 * 60)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # A down/misconfigured database must not kill the process: /health stays up and
    # /ready reports 503 until the database is reachable.
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            for stmt in MIGRATIONS:
                await conn.execute(text(stmt))
    except Exception:
        log.exception("Database unavailable at startup; check DATABASE_URL. Serving without tables.")
    try:
        await configure_bot()
    except Exception:
        log.exception("Telegram bot setup failed")
    task = asyncio.create_task(scheduler())
    yield
    task.cancel()


app = FastAPI(title="Nurses Oral Exam Trainer API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_headers=["Authorization", "Content-Type"],
    allow_methods=["*"],
)
app.include_router(health.router)
app.include_router(learner.router)
app.include_router(admin.router)
app.include_router(telegram.router)

import os

# API tests need a real PostgreSQL: TEST_DATABASE_URL=postgresql+asyncpg://user@host:port/db pytest
if os.environ.get("TEST_DATABASE_URL"):
    os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]
    os.environ.setdefault("BOT_TOKEN", "123:TEST")
    os.environ.setdefault("ADMIN_TELEGRAM_IDS", "999")

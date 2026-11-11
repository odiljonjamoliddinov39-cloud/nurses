from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import admin, courses, health, me
from .config import get_settings
from .db import Base, engine
from . import models  # noqa: F401  (register tables)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Dev/MVP bootstrap: create missing tables. TODO: replace with Alembic migrations.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(title="Nurses Oral Exam Trainer API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_headers=["Authorization", "Content-Type"],
    allow_methods=["*"],
)
app.include_router(health.router)
app.include_router(me.router)
app.include_router(admin.router)
app.include_router(courses.router)

# TODO (MVP): attempts (record/transcribe/grade), payments (request/approve/reject),
# plans, admin routers (users, questions, audio, settings, logs).

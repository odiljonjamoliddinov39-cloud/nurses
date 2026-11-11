from fastapi import FastAPI

from .api import courses, health, me

app = FastAPI(title="Nurses Oral Exam Trainer API")
app.include_router(health.router)
app.include_router(me.router)
app.include_router(courses.router)

# TODO (MVP): attempts (record/transcribe/grade), payments (request/approve/reject),
# plans, admin routers (users, questions, audio, settings, logs).

"""Background jobs (arq). TODO: transcribe_attempt, grade_attempt (with retry/backoff),
generate_tts, send_expiry_reminders, expire_subscriptions, send_broadcast, purge_old_recordings."""


async def ping(ctx) -> str:
    return "pong"


class WorkerSettings:
    functions = [ping]

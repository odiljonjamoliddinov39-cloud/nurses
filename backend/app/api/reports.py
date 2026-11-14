"""Admin reports: revenue, new vs renewed, conversion, hardest questions (JSON and Excel)."""
import io
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..models import Attempt, AttemptState, PaymentRequest, PaymentStatus, Plan, Question, User
from ..security import admin_user

router = APIRouter(prefix="/admin/reports", tags=["admin"])

TASHKENT = timezone(timedelta(hours=5))  # Uzbekistan has no daylight saving
MIN_ATTEMPTS_HARDEST = 3


async def build_report(session: AsyncSession, days: int) -> dict:
    if not 1 <= days <= 365:
        raise HTTPException(400, "days must be between 1 and 365")
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)

    paid = (await session.execute(
        select(PaymentRequest.id, PaymentRequest.user_id, PaymentRequest.amount, PaymentRequest.reviewed_at, Plan.name)
        .join(Plan, Plan.id == PaymentRequest.plan_id)
        .where(PaymentRequest.status == PaymentStatus.approved, PaymentRequest.reviewed_at >= since)
        .order_by(PaymentRequest.reviewed_at))).all()
    first_id = dict((await session.execute(
        select(PaymentRequest.user_id, func.min(PaymentRequest.id))
        .where(PaymentRequest.status == PaymentStatus.approved).group_by(PaymentRequest.user_id))).all())

    by_day: dict[date, list[int]] = {}
    by_plan: dict[str, list[int]] = {}
    new = [0, 0]
    renewed = [0, 0]
    for pid, user_id, amount, reviewed_at, plan_name in paid:
        d = reviewed_at.astimezone(TASHKENT).date()
        by_day.setdefault(d, []).append(amount)
        by_plan.setdefault(plan_name, []).append(amount)
        bucket = new if first_id.get(user_id) == pid else renewed
        bucket[0] += 1
        bucket[1] += amount

    today = now.astimezone(TASHKENT).date()
    revenue_by_day = []
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        amounts = by_day.get(d, [])
        revenue_by_day.append({"date": d.isoformat(), "amount": sum(amounts), "count": len(amounts)})

    total = sum(p[2] for p in paid)
    new_user_ids = set((await session.execute(select(User.id).where(User.created_at >= since))).scalars())
    paying = set((await session.execute(
        select(PaymentRequest.user_id).where(PaymentRequest.status == PaymentStatus.approved,
                                             PaymentRequest.user_id.in_(new_user_ids)))).scalars()) if new_user_ids else set()

    score = func.coalesce(Attempt.manual_score, Attempt.score)
    hardest_rows = (await session.execute(
        select(Question.number, Question.text, func.avg(score), func.count())
        .join(Question, Question.id == Attempt.question_id)
        .where(Attempt.state == AttemptState.graded, score.is_not(None), Question.is_active.is_(True))
        .group_by(Question.id, Question.number, Question.text)
        .having(func.count() >= MIN_ATTEMPTS_HARDEST)
        .order_by(func.avg(score), Question.number).limit(10))).all()

    answers = (await session.execute(select(func.count()).select_from(Attempt).where(
        Attempt.created_at >= since))).scalar_one()
    return {
        "days": days,
        "since": since.isoformat(),
        "totals": {"revenue": total, "payments": len(paid), "average_payment": round(total / len(paid)) if paid else 0,
                   "answers": answers},
        "revenue_by_day": revenue_by_day,
        "by_plan": sorted(({"plan": n, "amount": sum(a), "count": len(a)} for n, a in by_plan.items()),
                          key=lambda x: -x["amount"]),
        "new_vs_renewed": {"new": {"count": new[0], "amount": new[1]},
                           "renewed": {"count": renewed[0], "amount": renewed[1]}},
        "conversion": {"new_users": len(new_user_ids), "paying": len(paying),
                       "rate": round(len(paying) / len(new_user_ids), 3) if new_user_ids else 0.0},
        "hardest_questions": [{"number": n, "text": t, "average": round(float(a), 2), "attempts": c}
                              for n, t, a, c in hardest_rows],
    }


@router.get("")
async def report(days: int = 30, _: User = Depends(admin_user), session: AsyncSession = Depends(get_session)):
    return await build_report(session, days)


@router.get("/export")
async def export_report(days: int = 30, _: User = Depends(admin_user), session: AsyncSession = Depends(get_session)):
    from openpyxl import Workbook
    r = await build_report(session, days)
    wb = Workbook()
    ws = wb.active
    ws.title = "summary"
    ws.append(["period (days)", r["days"]])
    ws.append(["revenue (UZS)", r["totals"]["revenue"]])
    ws.append(["payments", r["totals"]["payments"]])
    ws.append(["average payment (UZS)", r["totals"]["average_payment"]])
    ws.append(["answers", r["totals"]["answers"]])
    ws.append(["new payments", r["new_vs_renewed"]["new"]["count"]])
    ws.append(["renewals", r["new_vs_renewed"]["renewed"]["count"]])
    ws.append(["new users", r["conversion"]["new_users"]])
    ws.append(["of them paying", r["conversion"]["paying"]])
    ws.append(["conversion", r["conversion"]["rate"]])
    for title, header, rows in (
        ("revenue_by_day", ["date", "amount", "payments"],
         [[d["date"], d["amount"], d["count"]] for d in r["revenue_by_day"]]),
        ("by_plan", ["plan", "amount", "payments"], [[p["plan"], p["amount"], p["count"]] for p in r["by_plan"]]),
        ("hardest_questions", ["number", "question", "average score", "attempts"],
         [[q["number"], q["text"], q["average"], q["attempts"]] for q in r["hardest_questions"]]),
    ):
        sheet = wb.create_sheet(title)
        sheet.append(header)
        for row in rows:
            sheet.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return Response(buf.getvalue(),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="report-{days}d.xlsx"'})

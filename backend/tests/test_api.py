"""End-to-end API tests against a real PostgreSQL (skipped without TEST_DATABASE_URL)."""
import hashlib
import hmac
import io
import json
import os
import time
from urllib.parse import urlencode

import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("TEST_DATABASE_URL"), reason="needs TEST_DATABASE_URL")

TOKEN = "123:TEST"
ADMIN = 999


def init_data(tg_id: int, name="Ana"):
    fields = {"auth_date": str(int(time.time())), "user": json.dumps({"id": tg_id, "first_name": name})}
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return {"Authorization": "tma " + urlencode(fields)}


def widget(tg_id: int):
    fields = {"id": tg_id, "first_name": "Boss", "auth_date": int(time.time())}
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    fields["hash"] = hmac.new(hashlib.sha256(TOKEN.encode()).digest(), check.encode(), hashlib.sha256).hexdigest()
    return fields


@pytest.fixture
async def client(monkeypatch):
    import httpx
    from app import telegram
    from app.db import Base, engine
    from app.main import app, MIGRATIONS
    from sqlalchemy import text

    sent = []

    async def fake_call(method, payload=None, files=None):
        sent.append((method, payload))
        return {"message_id": 1}

    monkeypatch.setattr(telegram, "call", fake_call)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        for m in MIGRATIONS:
            await conn.execute(text(m))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        c.sent = sent
        yield c
    await engine.dispose()


AUDIO = b"\x1aE\xdf\xa3" + b"\x00" * 5000  # fake webm bytes


async def test_full_flow(client):
    # admin signs in from the browser
    r = await client.post("/admin/login", json=widget(ADMIN))
    assert r.status_code == 200, r.text
    A = {"Authorization": "Bearer " + r.json()["token"]}
    assert (await client.post("/admin/login", json=widget(5))).status_code == 403

    # content
    cid = (await client.post("/admin/courses", headers=A, json={"name": {"uz": "Hamshira"}, "is_published": True})).json()["id"]
    tid = (await client.post(f"/admin/courses/{cid}/topics", headers=A, json={"name": "Asoslar"})).json()["id"]
    q1 = (await client.post("/admin/questions", headers=A, json={
        "course_id": cid, "topic_id": tid, "number": 1, "text": "Q1?", "model_answer": "A1",
        "key_points": [{"text": "k1", "weight": 1}, {"text": "k2", "weight": 3}]})).json()["id"]
    for n in range(2, 6):
        await client.post("/admin/questions", headers=A, json={"course_id": cid, "number": n, "text": f"Q{n}?",
                                                               "model_answer": "A"})
    await client.put("/admin/settings", headers=A, json={"free_questions": 2, "card_number": "8600 1234",
                                                         "card_holder": "ODILJON"})
    pid = (await client.post("/admin/plans", headers=A, json={"name": "1 oy", "days": 30, "price_uzs": 99000,
                                                              "course_ids": [cid]})).json()["id"]

    # learner
    U = init_data(42)
    me = (await client.get("/me", headers=U)).json()
    assert me["status"] == "guest" and me["is_admin"] is False
    qs = (await client.get(f"/courses/{cid}/questions", headers=U)).json()
    locked = [q["locked"] for q in qs["questions"]]
    assert locked == [False, False, True, True, True]

    r = await client.post("/attempts", headers=U, data={"question_id": str(q1)},
                          files={"audio": ("a.webm", AUDIO, "audio/webm")})
    assert r.status_code == 200, r.text
    att = r.json()
    assert att["state"] == "recorded" and len(att["key_points"]) == 2
    k2 = [k["id"] for k in att["key_points"] if k["text"] == "k2"]
    r = await client.post(f"/attempts/{att['id']}/self-grade", headers=U, json={"covered": k2})
    assert r.json()["score"] == 4.0 and r.json()["state"] == "graded"
    audio_id = r.json()["audio"]
    assert (await client.get(f"/files/{audio_id}", headers=U)).status_code == 200
    assert (await client.get(f"/files/{audio_id}", headers=init_data(43))).status_code == 404

    locked_q = qs["questions"][3]["id"]
    r = await client.post("/attempts", headers=U, data={"question_id": str(locked_q)},
                          files={"audio": ("a.webm", AUDIO, "audio/webm")})
    assert r.status_code == 402

    # payment
    assert (await client.get("/payment-info", headers=U)).json()["card_number"] == "8600 1234"
    r = await client.post("/payments", headers=U, data={"plan_id": str(pid)},
                          files={"receipt": ("r.png", b"\x89PNG" + b"0" * 100, "image/png")})
    assert r.status_code == 200, r.text
    assert (await client.get("/me", headers=U)).json()["status"] == "pending"
    assert any(m == "sendPhoto" and p["chat_id"] == ADMIN for m, p in client.sent)
    r = await client.post("/payments", headers=U, data={"plan_id": str(pid)},
                          files={"receipt": ("r.png", b"\x89PNG" + b"0" * 100, "image/png")})
    assert r.status_code == 409

    pays = (await client.get("/admin/payments", headers=A)).json()
    assert len(pays) == 1 and pays[0]["user"]["telegram_id"] == 42
    assert (await client.get(f"/admin/files/{pays[0]['receipt']}", headers=A)).status_code == 200
    r = await client.post(f"/admin/payments/{pays[0]['id']}/approve", headers=A)
    assert r.status_code == 200, r.text
    assert (await client.post(f"/admin/payments/{pays[0]['id']}/approve", headers=A)).status_code == 409
    me = (await client.get("/me", headers=U)).json()
    assert me["status"] == "subscriber" and me["subscription"]["plan"] == "1 oy"
    assert all(not q["locked"] for q in (await client.get(f"/courses/{cid}/questions", headers=U)).json()["questions"])
    assert any(m == "sendMessage" and p["chat_id"] == 42 for m, p in client.sent)

    # admin review, users, dashboard, logs
    atts = (await client.get("/admin/attempts", headers=A)).json()
    r = await client.put(f"/admin/attempts/{atts[0]['id']}/score", headers=A, json={"score": 3.3})
    assert r.status_code == 200
    mine = (await client.get("/attempts", headers=U)).json()
    assert mine["items"][0]["score"] == 3.5
    users = (await client.get("/admin/users", headers=A)).json()
    uid = [u for u in users if u["telegram_id"] == 42][0]["id"]
    detail = (await client.get(f"/admin/users/{uid}", headers=A)).json()
    assert detail["status"] == "subscriber" and len(detail["subscriptions"]) == 1
    r = await client.post(f"/admin/users/{uid}/grant", headers=A, json={"days": 10, "reason": "bonus"})
    assert r.status_code == 200
    await client.post(f"/admin/users/{uid}/block", headers=A, json={"blocked": True})
    assert (await client.get("/me", headers=U)).status_code == 403
    await client.post(f"/admin/users/{uid}/block", headers=A, json={"blocked": False})
    assert (await client.get("/me", headers=U)).json()["status"] == "subscriber"
    dash = (await client.get("/admin/dashboard", headers=A)).json()
    assert dash["revenue_month"] == 99000 and dash["active_subscribers"] == 1
    assert len((await client.get("/admin/logs", headers=A)).json()) >= 5

    # admin endpoints refuse learners
    assert (await client.get("/admin/dashboard", headers=U)).status_code == 403
    assert (await client.get("/admin/dashboard")).status_code == 401


async def test_excel_import_export(client):
    from openpyxl import Workbook
    A = {"Authorization": "Bearer " + (await client.post("/admin/login", json=widget(ADMIN))).json()["token"]}
    cid = (await client.post("/admin/courses", headers=A, json={"name": {"uz": "C"}})).json()["id"]
    wb = Workbook()
    ws = wb.active
    ws.append(["№", "Mavzu", "Savol", "Javob", "Kalit fikrlar"])
    ws.append([1, "T1", "Birinchi?", "Javob 1", "a\nb | 2"])
    ws.append([2, "T1", "Ikkinchi?", "Javob 2", ""])
    ws.append([None, None, None, None, None])
    buf = io.BytesIO()
    wb.save(buf)
    r = await client.post(f"/admin/courses/{cid}/import", headers=A,
                          files={"file": ("q.xlsx", buf.getvalue(), "application/octet-stream")})
    assert r.json() == {"created": 2, "updated": 0}, r.text
    qs = (await client.get(f"/admin/courses/{cid}/questions", headers=A)).json()
    assert [k["weight"] for k in qs[0]["key_points"]] == [1.0, 2.0]
    r = await client.post(f"/admin/courses/{cid}/import", headers=A,
                          files={"file": ("q.xlsx", buf.getvalue(), "application/octet-stream")})
    assert r.json() == {"created": 0, "updated": 2}
    r = await client.get(f"/admin/courses/{cid}/export", headers=A)
    assert r.status_code == 200 and r.content[:2] == b"PK"


async def test_webhook_payment_buttons(client):
    from app.telegram import webhook_secret
    H = {"X-Telegram-Bot-Api-Secret-Token": webhook_secret(TOKEN)}
    assert (await client.post("/telegram/webhook", json={})).status_code == 403
    msg = {"message": {"message_id": 1, "from": {"id": 77, "first_name": "Zuhra"},
                       "chat": {"id": 77, "type": "private"}, "text": "/start"}}
    assert (await client.post("/telegram/webhook", headers=H, json=msg)).status_code == 200
    assert client.sent[-1][1]["reply_markup"]["keyboard"][0][0]["request_contact"] is True
    contact = {"message": {"message_id": 2, "from": {"id": 77}, "chat": {"id": 77, "type": "private"},
                           "contact": {"user_id": 77, "phone_number": "+998901112233"}}}
    await client.post("/telegram/webhook", headers=H, json=contact)

    A = {"Authorization": "Bearer " + (await client.post("/admin/login", json=widget(ADMIN))).json()["token"]}
    pid = (await client.post("/admin/plans", headers=A, json={"name": "P", "days": 7, "price_uzs": 1})).json()["id"]
    U = init_data(77, "Zuhra")
    me = (await client.get("/me", headers=U)).json()
    assert me["phone"] == "+998901112233"
    await client.post("/payments", headers=U, data={"plan_id": str(pid)},
                      files={"receipt": ("r.jpg", b"\xff\xd8" + b"0" * 100, "image/jpeg")})
    req_id = (await client.get("/admin/payments", headers=A)).json()[0]["id"]
    cb = {"callback_query": {"id": "c1", "from": {"id": 5}, "data": f"pay:a:{req_id}",
                             "message": {"message_id": 9, "chat": {"id": 5}, "caption": "x", "photo": [{}]}}}
    await client.post("/telegram/webhook", headers=H, json=cb)
    assert (await client.get("/me", headers=U)).json()["status"] == "pending"  # non-admin button ignored
    cb["callback_query"]["from"]["id"] = ADMIN
    cb["callback_query"]["data"] = f"pay:x:{req_id}:amount"
    await client.post("/telegram/webhook", headers=H, json=cb)
    me = (await client.get("/me", headers=U)).json()
    assert me["status"] == "guest" and me["last_payment"]["reject_reason"] == "amount"


async def test_subscription_job(client):
    from datetime import timedelta
    from app.db import SessionLocal
    from app.main import subscription_job
    from app.models import Subscription, SubscriptionSource, User
    from app.services import now_utc
    await client.get("/me", headers=init_data(88))
    async with SessionLocal() as s:
        from sqlalchemy import select
        u = (await s.execute(select(User).where(User.telegram_id == 88))).scalar_one()
        s.add(Subscription(user_id=u.id, starts_at=now_utc() - timedelta(days=30),
                           ends_at=now_utc() + timedelta(hours=20), source=SubscriptionSource.gift))
        await s.commit()
    await subscription_job()
    await subscription_job()
    reminders = [p for m, p in client.sent if m == "sendMessage" and p["chat_id"] == 88]
    assert len(reminders) == 1

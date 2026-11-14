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


async def seed_course(client, A, n=6, topics=2):
    cid = (await client.post("/admin/courses", headers=A, json={"name": {"uz": "Kurs"}, "is_published": True})).json()["id"]
    tids = [(await client.post(f"/admin/courses/{cid}/topics", headers=A, json={"name": f"T{i}"})).json()["id"]
            for i in range(topics)]
    qids = []
    for i in range(1, n + 1):
        qids.append((await client.post("/admin/questions", headers=A, json={
            "course_id": cid, "topic_id": tids[i % topics], "number": i, "text": f"Q{i}?", "model_answer": f"A{i}",
            "key_points": [{"text": "k1", "weight": 1}]})).json()["id"])
    return cid, tids, qids


async def answer(client, U, qid, covered=True):
    att = (await client.post("/attempts", headers=U, data={"question_id": str(qid)},
                             files={"audio": ("a.webm", AUDIO, "audio/webm")})).json()
    ids = [k["id"] for k in att["key_points"]] if covered else []
    return (await client.post(f"/attempts/{att['id']}/self-grade", headers=U, json={"covered": ids})).json()


async def test_favourites_stats_mock_learn(client):
    A = {"Authorization": "Bearer " + (await client.post("/admin/login", json=widget(ADMIN))).json()["token"]}
    cid, tids, qids = await seed_course(client, A)
    await client.put("/admin/settings", headers=A, json={"free_questions": 3})
    U = init_data(77)

    # favourites toggle and show up in the question list
    assert (await client.post(f"/questions/{qids[1]}/favourite", headers=U, json={"on": True})).json() == {"favourite": True}
    assert (await client.post(f"/questions/{qids[1]}/favourite", headers=U, json={"on": True})).status_code == 200  # idempotent
    qs = (await client.get(f"/courses/{cid}/questions", headers=U)).json()["questions"]
    assert [q["favourite"] for q in qs] == [False, True, False, False, False, False]
    assert (await client.get(f"/courses/{cid}/questions", headers=init_data(78))).json()["questions"][1]["favourite"] is False
    await client.post(f"/questions/{qids[1]}/favourite", headers=U, json={"on": False})
    assert not any(q["favourite"] for q in (await client.get(f"/courses/{cid}/questions", headers=U)).json()["questions"])
    assert (await client.post("/questions/999999/favourite", headers=U, json={"on": True})).status_code == 404

    # stats: empty first, then after two graded answers (one full score, one zero)
    st = (await client.get(f"/stats?course_id={cid}", headers=U)).json()
    assert st["total"] == 6 and st["answered"] == 0 and st["average"] is None and st["streak"] == 0
    assert len(st["trend"]) == 14 and st["weakest_topics"] == []
    assert (await answer(client, U, qids[0], covered=True))["score"] == 5.0
    assert (await answer(client, U, qids[1], covered=False))["score"] == 0.0
    st = (await client.get(f"/stats?course_id={cid}", headers=U)).json()
    assert st["answered"] == 2 and st["average"] == 2.5 and st["streak"] == 1
    assert st["trend"][-1]["count"] == 2 and st["trend"][-1]["avg"] == 2.5
    assert st["weakest_topics"][0]["avg"] == 0.0 and st["weakest_topics"][0]["answered"] == 1
    assert all(w["avg"] < 4 for w in st["weakest_topics"])  # a strong topic is not "weakest"
    assert (await client.get("/stats?course_id=999999", headers=U)).status_code == 404
    assert (await client.get("/stats", headers=U)).json()["answered"] == 2  # defaults to the first published course
    assert (await client.get("/stats", headers=init_data(79))).json()["total"] == 6
    assert (await client.get(f"/questions/{qids[0]}", headers=U)).json()["favourite"] is False

    # mock exam: only the 3 free questions are available, count is clamped to 3-5
    m = (await client.get(f"/courses/{cid}/mock?count=5", headers=U)).json()
    assert len(m["questions"]) == 3 and {q["id"] for q in m["questions"]} == set(qids[:3])
    assert m["total_seconds"] == 3 * m["per_answer_seconds"]
    assert len((await client.get(f"/courses/{cid}/mock?count=1", headers=U)).json()["questions"]) == 3

    # learn playlist: free questions only, with model answers
    items = (await client.get(f"/courses/{cid}/learn", headers=U)).json()["items"]
    assert [i["number"] for i in items] == [1, 2, 3] and items[0]["model_answer"] == "A1"

    # blocked-by-paywall questions never leak: with no free questions the lists are empty / 404
    await client.put("/admin/settings", headers=A, json={"free_questions": 0})
    assert (await client.get(f"/courses/{cid}/learn", headers=U)).json()["items"] == []
    assert (await client.get(f"/courses/{cid}/mock", headers=U)).status_code == 404


async def test_miniapp_url_falls_back_to_env(client, monkeypatch):
    from app.config import get_settings
    from app.db import SessionLocal
    from app.services import get_setting, put_settings

    async with SessionLocal() as s:
        assert await get_setting(s, "miniapp_url") == ""
    monkeypatch.setattr(get_settings(), "miniapp_url", "https://env.example.app")
    async with SessionLocal() as s:
        assert await get_setting(s, "miniapp_url") == "https://env.example.app"
        await put_settings(s, {"miniapp_url": "https://admin.example.app"})  # the admin setting wins
        await s.commit()
    async with SessionLocal() as s:
        assert await get_setting(s, "miniapp_url") == "https://admin.example.app"


async def test_test_mode_mcq(client):
    A = {"Authorization": "Bearer " + (await client.post("/admin/login", json=widget(ADMIN))).json()["token"]}
    cid, tids, qids = await seed_course(client, A, n=4)
    await client.put("/admin/settings", headers=A, json={"free_questions": 3})
    U = init_data(88)

    def body(i, options, **kw):
        return {"course_id": cid, "number": i, "text": f"Q{i}?", "model_answer": "A", "explanation": kw.get("explanation"),
                "mcq_options": options}

    good = [{"text": "Right", "is_correct": True}, {"text": "Wrong 1"}, {"text": "Wrong 2"}]
    # validation: need 2-6 options, exactly one correct, all different
    for bad in ([{"text": "only", "is_correct": True}],
                [{"text": "a", "is_correct": True}, {"text": "b", "is_correct": True}],
                [{"text": "a"}, {"text": "b"}],
                [{"text": "a", "is_correct": True}, {"text": "A"}],
                [{"text": str(i), "is_correct": i == 0} for i in range(7)]):
        assert (await client.put(f"/admin/questions/{qids[0]}", headers=A, json=body(1, bad))).status_code == 400
    assert (await client.put(f"/admin/questions/{qids[0]}", headers=A, json=body(1, good, explanation="Because."))).status_code == 200
    assert (await client.put(f"/admin/questions/{qids[1]}", headers=A, json=body(2, good))).status_code == 200
    assert (await client.put(f"/admin/questions/{qids[3]}", headers=A, json=body(4, good))).status_code == 200  # question 4 is locked (free=3)

    listed = (await client.get(f"/admin/courses/{cid}/questions", headers=A)).json()
    assert [o["is_correct"] for o in listed[0]["mcq_options"]] == [True, False, False]
    # editing again replaces the options instead of piling up
    assert (await client.put(f"/admin/questions/{qids[0]}", headers=A, json=body(1, good, explanation="Because."))).status_code == 200
    assert len((await client.get(f"/admin/courses/{cid}/questions", headers=A)).json()[0]["mcq_options"]) == 3

    # learner: only questions with options AND open to this user; correct answers are not revealed
    t = (await client.get(f"/courses/{cid}/test?count=10", headers=U)).json()
    assert {q["id"] for q in t["questions"]} == {qids[0], qids[1]} and t["available"] == 2
    assert all("is_correct" not in o for q in t["questions"] for o in q["options"])
    q1 = next(q for q in t["questions"] if q["id"] == qids[0])
    assert sorted(o["text"] for o in q1["options"]) == ["Right", "Wrong 1", "Wrong 2"]
    right = next(o["id"] for o in q1["options"] if o["text"] == "Right")
    wrong = next(o["id"] for o in q1["options"] if o["text"] == "Wrong 1")

    r = (await client.post(f"/questions/{qids[0]}/mcq-answer", headers=U, json={"option_id": wrong})).json()
    assert r == {"correct": False, "correct_option_id": right, "explanation": "Because."}
    assert (await client.post(f"/questions/{qids[0]}/mcq-answer", headers=U, json={"option_id": right})).json()["correct"] is True
    assert (await client.post(f"/questions/{qids[0]}/mcq-answer", headers=U, json={"option_id": 999999})).status_code == 400
    # an option of another question is not accepted, and a locked question cannot be probed for its answer
    assert (await client.post(f"/questions/{qids[1]}/mcq-answer", headers=U, json={"option_id": right})).status_code == 400
    assert (await client.post(f"/questions/{qids[3]}/mcq-answer", headers=U, json={"option_id": right})).status_code == 402
    # test answers are not oral attempts: statistics stay untouched
    assert (await client.get(f"/stats?course_id={cid}", headers=U)).json()["answered"] == 0

    # deleting a question removes its options too
    assert (await client.delete(f"/admin/questions/{qids[0]}", headers=A)).status_code == 200
    after = (await client.get(f"/courses/{cid}/test?count=10", headers=U)).json()["questions"]
    assert {q["id"] for q in after} == {qids[1], qids[3]}  # q1 is gone; q4 became one of the 3 free questions


async def pay_and_approve(client, A, U, plan_id):
    r = await client.post("/payments", headers=U, data={"plan_id": str(plan_id)},
                          files={"receipt": ("r.png", b"\x89PNG" + b"0" * 100, "image/png")})
    assert r.status_code == 200, r.text
    pays = (await client.get("/admin/payments?status=pending", headers=A)).json()
    assert (await client.post(f"/admin/payments/{pays[0]['id']}/approve", headers=A)).status_code == 200


async def test_reports(client):
    import io as _io
    A = {"Authorization": "Bearer " + (await client.post("/admin/login", json=widget(ADMIN))).json()["token"]}
    cid, tids, qids = await seed_course(client, A, n=4)
    await client.put("/admin/settings", headers=A, json={"free_questions": 4})
    monthly = (await client.post("/admin/plans", headers=A, json={"name": "1 oy", "days": 30, "price_uzs": 100000, "course_ids": [cid]})).json()["id"]
    yearly = (await client.post("/admin/plans", headers=A, json={"name": "Imtihongacha", "days": 90, "price_uzs": 250000, "course_ids": [cid]})).json()["id"]

    empty = (await client.get("/admin/reports?days=7", headers=A)).json()
    assert empty["totals"] == {"revenue": 0, "payments": 0, "average_payment": 0, "answers": 0}
    assert len(empty["revenue_by_day"]) == 7 and empty["by_plan"] == [] and empty["hardest_questions"] == []

    ana, bek, cara = init_data(201, "Ana"), init_data(202, "Bek"), init_data(203, "Cara")
    await pay_and_approve(client, A, ana, monthly)    # Ana: new
    await pay_and_approve(client, A, ana, yearly)     # Ana again: renewal
    await pay_and_approve(client, A, bek, monthly)    # Bek: new
    await client.get("/me", headers=cara)             # Cara registers but never pays

    # hardest question: three zero-score answers on question 2, one full score on question 1
    for _ in range(3):
        await answer(client, ana, qids[1], covered=False)
    await answer(client, ana, qids[0], covered=True)

    r = (await client.get("/admin/reports?days=30", headers=A)).json()
    assert r["totals"]["revenue"] == 450000 and r["totals"]["payments"] == 3 and r["totals"]["average_payment"] == 150000
    assert r["totals"]["answers"] == 4
    assert r["new_vs_renewed"] == {"new": {"count": 2, "amount": 200000}, "renewed": {"count": 1, "amount": 250000}}
    assert {p["plan"]: (p["amount"], p["count"]) for p in r["by_plan"]} == {"1 oy": (200000, 2), "Imtihongacha": (250000, 1)}
    assert r["by_plan"][0]["plan"] == "Imtihongacha"  # sorted by revenue
    assert len(r["revenue_by_day"]) == 30 and r["revenue_by_day"][-1]["amount"] == 450000 and r["revenue_by_day"][-1]["count"] == 3
    assert r["conversion"]["paying"] == 2 and r["conversion"]["new_users"] >= 3 and 0 < r["conversion"]["rate"] < 1
    # only questions with 3+ graded answers are listed
    assert [q["number"] for q in r["hardest_questions"]] == [2] and r["hardest_questions"][0]["average"] == 0.0

    for bad in (0, 366, -5):
        assert (await client.get(f"/admin/reports?days={bad}", headers=A)).status_code == 400
    assert (await client.get("/admin/reports", headers=ana)).status_code in (401, 403)  # learners cannot read reports

    x = await client.get("/admin/reports/export?days=30", headers=A)
    assert x.status_code == 200 and "spreadsheetml" in x.headers["content-type"]
    from openpyxl import load_workbook
    wb = load_workbook(_io.BytesIO(x.content))
    assert wb.sheetnames == ["summary", "revenue_by_day", "by_plan", "hardest_questions"]
    assert wb["summary"]["B2"].value == 450000 and wb["by_plan"].max_row == 3


async def test_broadcasts(client, monkeypatch):
    from datetime import datetime, timedelta, timezone
    from app import broadcasts as bc, telegram
    from app.db import SessionLocal
    from app.models import Broadcast
    from sqlalchemy import update

    monkeypatch.setattr(bc, "SEND_PAUSE", 0)
    A = {"Authorization": "Bearer " + (await client.post("/admin/login", json=widget(ADMIN))).json()["token"]}
    cid, _, _ = await seed_course(client, A, n=3)
    ids = {}
    for name, tg in (("ana", 401), ("bek", 402), ("cara", 403), ("dina", 404)):
        await client.get("/me", headers=init_data(tg, name))
    users = {u["telegram_id"]: u["id"] for u in (await client.get("/admin/users", headers=A)).json()}
    # ana: active subscriber, cara: expired (cancelled), dina: blocked, bek: guest on the course
    await client.post(f"/admin/users/{users[401]}/grant", headers=A, json={"days": 30})
    await client.post(f"/admin/users/{users[403]}/grant", headers=A, json={"days": 30})
    cara_sub = (await client.get(f"/admin/users/{users[403]}", headers=A)).json()["subscriptions"][0]["id"]
    await client.post(f"/admin/subscriptions/{cara_sub}/cancel", headers=A)
    await client.post(f"/admin/users/{users[404]}/block", headers=A, json={"blocked": True})
    assert (await client.patch("/me", headers=init_data(402, "bek"), json={"course_id": cid})).status_code == 200

    async def count(segment):
        return (await client.get(f"/admin/broadcasts/preview?segment={segment}", headers=A)).json()["count"]

    # segments: the blocked user is never reached; the admin (999) is a guest like bek
    assert await count("all") == 4        # ana, bek, cara, admin
    assert await count("subscribers") == 1
    assert await count("expired") == 1
    assert await count("guests") == 2     # bek and the admin
    assert await count(f"course:{cid}") == 1
    assert (await client.get("/admin/broadcasts/preview?segment=nope", headers=A)).status_code == 400

    # validation
    base = {"text": "Salom!", "segment": "all"}
    for bad in ({**base, "text": ""}, {**base, "segment": "vip"}, {**base, "segment": "course:9999"},
                {**base, "button_text": "Open"}, {**base, "button_text": "Open", "button_url": "http://x.example"},
                {**base, "scheduled_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()}):
        assert (await client.post("/admin/broadcasts", headers=A, json=bad)).status_code in (400, 404, 422), bad
    assert (await client.get("/admin/broadcasts", headers=init_data(401, "ana"))).status_code in (401, 403)

    # a draft sends nothing; "test" goes to the admin only
    client.sent.clear()
    b = (await client.post("/admin/broadcasts", headers=A, json={
        **base, "segment": "subscribers", "button_text": "Ochish", "button_url": "https://t.me/example"})).json()
    assert b["status"] == "draft" and b["scheduled_at"] is None and client.sent == []
    assert (await client.post(f"/admin/broadcasts/{b['id']}/test", headers=A)).json() == {"ok": True}
    assert [(m, p["chat_id"]) for m, p in client.sent] == [("sendMessage", ADMIN)]
    assert client.sent[0][1]["reply_markup"]["inline_keyboard"][0][0] == {"text": "Ochish", "url": "https://t.me/example"}

    # send now: only the subscriber gets it, progress is recorded
    client.sent.clear()
    assert (await client.post(f"/admin/broadcasts/{b['id']}/send", headers=A)).status_code == 200
    assert [(m, p["chat_id"]) for m, p in client.sent] == [("sendMessage", 401)]
    done = next(x for x in (await client.get("/admin/broadcasts", headers=A)).json() if x["id"] == b["id"])
    assert (done["status"], done["total"], done["sent"], done["failed"]) == ("sent", 1, 1, 0) and done["sent_at"]
    # a sent broadcast cannot be changed, resent or deleted
    assert (await client.post(f"/admin/broadcasts/{b['id']}/send", headers=A)).status_code == 409
    assert (await client.put(f"/admin/broadcasts/{b['id']}", headers=A, json=base)).status_code == 409
    assert (await client.delete(f"/admin/broadcasts/{b['id']}", headers=A)).status_code == 409

    # failed deliveries are counted, not fatal
    real_call = telegram.call

    async def flaky(method, payload=None, files=None):
        return None if payload and payload.get("chat_id") == 402 else await real_call(method, payload, files)

    monkeypatch.setattr(telegram, "call", flaky)
    client.sent.clear()
    r = (await client.post("/admin/broadcasts", headers=A, json={**base, "send_now": True})).json()
    after = next(x for x in (await client.get("/admin/broadcasts", headers=A)).json() if x["id"] == r["id"])
    assert (after["total"], after["sent"], after["failed"], after["status"]) == (4, 3, 1, "sent")
    monkeypatch.setattr(telegram, "call", real_call)  # deliveries work again

    # image: sent as a photo with the text as caption; long text goes as photo + message
    png = ("a.png", b"\x89PNG" + b"0" * 100, "image/png")
    img = (await client.post("/admin/broadcasts", headers=A, json={**base, "segment": f"course:{cid}"})).json()
    assert (await client.post(f"/admin/broadcasts/{img['id']}/image", headers=A, files={"image": png})).json()["image"]
    assert (await client.post(f"/admin/broadcasts/{img['id']}/image", headers=A,
                              files={"image": ("a.txt", b"hello", "text/plain")})).status_code == 415
    client.sent.clear()
    await client.post(f"/admin/broadcasts/{img['id']}/send", headers=A)
    assert [(m, p["chat_id"], p.get("caption")) for m, p in client.sent] == [("sendPhoto", 402, "Salom!")]
    long_text = "x" * 1500
    img2 = (await client.post("/admin/broadcasts", headers=A, json={**base, "text": long_text, "segment": "subscribers"})).json()
    await client.post(f"/admin/broadcasts/{img2['id']}/image", headers=A, files={"image": png})
    client.sent.clear()
    await client.post(f"/admin/broadcasts/{img2['id']}/send", headers=A)
    assert [m for m, _ in client.sent] == ["sendPhoto", "sendMessage"] and client.sent[1][1]["text"] == long_text

    # scheduled: waits until its time, then is claimed exactly once
    soon = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    s = (await client.post("/admin/broadcasts", headers=A, json={**base, "segment": "expired", "scheduled_at": soon})).json()
    assert s["status"] == "scheduled"
    client.sent.clear()
    assert await bc.dispatch_due() == 0 and client.sent == []
    async with SessionLocal() as session:   # time passes
        await session.execute(update(Broadcast).where(Broadcast.id == s["id"]).values(
            scheduled_at=datetime.now(timezone.utc) - timedelta(minutes=1)))
        await session.commit()
    assert await bc.dispatch_due() == 1
    assert [(m, p["chat_id"]) for m, p in client.sent] == [("sendMessage", 403)]
    assert await bc.dispatch_due() == 0     # not sent twice
    # scheduled ones can still be edited and deleted
    s2 = (await client.post("/admin/broadcasts", headers=A, json={**base, "scheduled_at": soon})).json()
    assert (await client.put(f"/admin/broadcasts/{s2['id']}", headers=A, json=base)).json()["status"] == "draft"
    assert (await client.delete(f"/admin/broadcasts/{s2['id']}", headers=A)).status_code == 200


async def test_promo_codes(client):
    from datetime import datetime, timedelta, timezone
    A = {"Authorization": "Bearer " + (await client.post("/admin/login", json=widget(ADMIN))).json()["token"]}
    cid, _, _ = await seed_course(client, A, n=2)
    plan = (await client.post("/admin/plans", headers=A, json={"name": "1 oy", "days": 30, "price_uzs": 100000, "course_ids": [cid]})).json()["id"]
    ana, bek = init_data(501, "Ana"), init_data(502, "Bek")

    def make(code, kind="percent", value=20, **kw):
        return client.post("/admin/promos", headers=A, json={"code": code, "kind": kind, "value": value, **kw})

    # creating: stored upper-case, unique, validated
    r = await make("yoz-20")
    assert r.status_code == 200 and r.json()["code"] == "YOZ-20" and r.json()["used_count"] == 0
    assert (await make("YOZ-20")).status_code == 409
    for bad in (dict(code="ab"), dict(code="has space"), dict(code="OK1", value=0), dict(code="OK2", value=100),
                dict(code="OK3", kind="other")):
        assert (await make(**bad)).status_code in (400, 422), bad

    # checking as a learner
    async def check(code, who=ana):
        return (await client.get(f"/promo/check?code={code}&plan_id={plan}", headers=who)).json()

    assert await check("yoz-20") == {"valid": True, "code": "YOZ-20", "discount": 20000, "final": 80000}  # case-insensitive
    assert await check("nope") == {"valid": False, "reason": "unknown"}
    await make("FIX30", "fixed", 30000)
    assert (await check("FIX30"))["final"] == 70000
    await make("ALL", "fixed", 100000)
    assert await check("ALL") == {"valid": False, "reason": "too_big"}      # the plan would cost nothing
    await make("OLD", expires_at=(datetime.now(timezone.utc) - timedelta(days=1)).isoformat())
    assert await check("OLD") == {"valid": False, "reason": "expired"}
    await make("OFF", is_active=False)
    assert await check("OFF") == {"valid": False, "reason": "inactive"}
    assert (await client.get("/promo/check?code=X&plan_id=9999", headers=ana)).status_code == 404

    # paying with a code: discounted amount, use reserved, admin and bot see it
    receipt = {"receipt": ("r.png", b"\x89PNG" + b"0" * 100, "image/png")}
    r = await client.post("/payments", headers=ana, data={"plan_id": str(plan), "promo": "yoz-20"}, files=receipt)
    assert r.status_code == 200, r.text
    pay = (await client.get("/admin/payments", headers=A)).json()[0]
    assert (pay["amount"], pay["discount"], pay["promo"]) == (80000, 20000, "YOZ-20")
    assert [p for p in (await client.get("/admin/promos", headers=A)).json() if p["code"] == "YOZ-20"][0]["used_count"] == 1
    assert any("Promo YOZ-20" in (p.get("caption") or "") for m, p in client.sent if m == "sendPhoto")
    assert (await client.get("/payments", headers=ana)).json()[0]["promo"] == "YOZ-20"
    # one use per person while a payment with it is open
    assert await check("yoz-20") == {"valid": False, "reason": "already_used"}
    # an invalid code stops the payment and uses nothing
    bad = await client.post("/payments", headers=bek, data={"plan_id": str(plan), "promo": "OLD"}, files=receipt)
    assert bad.status_code == 400 and "expired" in bad.text
    assert (await client.get("/admin/payments?status=all", headers=A)).json().__len__() == 1

    # rejecting gives the use back and lets the same person try again
    assert (await client.post(f"/admin/payments/{pay['id']}/reject", headers=A, json={"reason": "amount"})).status_code == 200
    assert [p for p in (await client.get("/admin/promos", headers=A)).json() if p["code"] == "YOZ-20"][0]["used_count"] == 0
    assert (await check("yoz-20"))["valid"] is True

    # usage limit: the second person is refused once it is used up; approval keeps it counted
    await make("ONCE", value=50, max_uses=1)
    assert (await client.post("/payments", headers=ana, data={"plan_id": str(plan), "promo": "ONCE"}, files=receipt)).status_code == 200
    assert await check("ONCE", bek) == {"valid": False, "reason": "used_up"}
    assert (await client.post("/payments", headers=bek, data={"plan_id": str(plan), "promo": "ONCE"}, files=receipt)).status_code == 400
    pend = (await client.get("/admin/payments", headers=A)).json()[0]
    assert pend["amount"] == 50000
    assert (await client.post(f"/admin/payments/{pend['id']}/approve", headers=A)).status_code == 200
    rep = (await client.get("/admin/reports?days=7", headers=A)).json()
    assert rep["totals"]["revenue"] == 50000      # revenue is what was actually paid

    # editing and deleting rules
    promos = {p["code"]: p for p in (await client.get("/admin/promos", headers=A)).json()}
    once = promos["ONCE"]
    base = {"code": "ONCE", "kind": "percent", "value": 50}
    assert (await client.put(f"/admin/promos/{once['id']}", headers=A, json={**base, "value": 10})).status_code == 409   # used: value is frozen
    assert (await client.put(f"/admin/promos/{once['id']}", headers=A, json={**base, "max_uses": 5})).status_code == 200  # limit can grow
    assert (await client.delete(f"/admin/promos/{once['id']}", headers=A)).status_code == 409                           # used: switch off instead
    assert (await client.put(f"/admin/promos/{once['id']}", headers=A, json={**base, "max_uses": 5, "is_active": False})).json()["is_active"] is False
    assert (await client.put(f"/admin/promos/{promos['FIX30']['id']}", headers=A,
                             json={"code": "FIX30", "kind": "fixed", "value": 25000})).json()["value"] == 25000      # unused: can change
    assert (await client.delete(f"/admin/promos/{promos['FIX30']['id']}", headers=A)).status_code == 200
    assert (await client.get("/admin/promos", headers=ana)).status_code in (401, 403)


async def test_promo_one_use_race(client):
    import asyncio
    A = {"Authorization": "Bearer " + (await client.post("/admin/login", json=widget(ADMIN))).json()["token"]}
    cid, _, _ = await seed_course(client, A, n=1)
    plan = (await client.post("/admin/plans", headers=A, json={"name": "P", "days": 30, "price_uzs": 100000, "course_ids": [cid]})).json()["id"]
    await client.post("/admin/promos", headers=A, json={"code": "RACE", "kind": "percent", "value": 10, "max_uses": 1})
    receipt = lambda: {"receipt": ("r.png", b"\x89PNG" + b"0" * 100, "image/png")}
    users = [init_data(600 + i, f"U{i}") for i in range(6)]
    results = await asyncio.gather(*[client.post("/payments", headers=u, data={"plan_id": str(plan), "promo": "RACE"}, files=receipt())
                                     for u in users])
    ok = [r for r in results if r.status_code == 200]
    assert len(ok) == 1, [r.status_code for r in results]          # exactly one winner out of six
    assert all(r.status_code == 400 for r in results if r is not ok[0])
    promo = (await client.get("/admin/promos", headers=A)).json()[0]
    assert promo["used_count"] == 1
    discounted = [p for p in (await client.get("/admin/payments?status=all", headers=A)).json() if p["promo"]]
    assert len(discounted) == 1                                    # the losers created no payment request


async def test_ai_voice(client, monkeypatch):
    from app import tts
    from app.api import voice
    monkeypatch.setattr(voice, "PAUSE", 0)
    A = {"Authorization": "Bearer " + (await client.post("/admin/login", json=widget(ADMIN))).json()["token"]}
    cid, _, qids = await seed_course(client, A, n=4)
    await client.put("/admin/settings", headers=A, json={"free_questions": 4})
    U = init_data(801, "Ana")

    calls = []

    async def fake(text, *, key, region, voice, transport=None):
        if not key or not region:  # like the real client
            raise tts.TTSError("set the Azure Speech key and region in Settings first", fatal=True)
        calls.append((text, key, region, voice))
        if text == "A3":
            raise tts.TTSError("Azure refused the request")
        return b"ID3fake:" + text.encode()

    monkeypatch.setattr(tts, "synthesize", fake)

    # not configured yet: clear message, nothing is called
    assert (await client.get("/admin/tts/status", headers=A)).json()["configured"] is False
    r = await client.post(f"/admin/questions/{qids[0]}/tts", headers=A, json={"kind": "question"})
    assert r.status_code == 400 and "Settings" in r.text and calls == []
    assert (await client.post(f"/admin/courses/{cid}/tts-missing", headers=A, json={})).status_code == 400
    await client.put("/admin/settings", headers=A, json={"azure_tts_key": "SECRET-KEY-1234", "azure_tts_region": "WestEurope"})
    st = (await client.get("/admin/tts/status", headers=A)).json()
    assert st["configured"] is True and st["voices"]["uz"] == "uz-UZ-MadinaNeural"
    assert "SECRET-KEY" not in (await client.get("/admin/settings", headers=A)).text   # the key is never sent back

    # one clip: stored, attached, playable by a learner who may open the question
    r = await client.post(f"/admin/questions/{qids[0]}/tts", headers=A, json={"kind": "question", "lang": "ru"})
    assert r.status_code == 200, r.text
    assert calls[-1] == ("Q1?", "SECRET-KEY-1234", "westeurope", "ru-RU-SvetlanaNeural")   # region normalised, Russian voice
    listed = (await client.get(f"/admin/courses/{cid}/questions", headers=A)).json()
    assert listed[0]["question_audio"] == r.json()["file"] and listed[0]["answer_audio"] is None
    f = await client.get(f"/files/{r.json()['file']}", headers=U)
    assert f.status_code == 200 and f.content == b"ID3fake:Q1?" and f.headers["content-type"] == "audio/mpeg"

    # a teacher's recording has priority: refused unless explicitly overwritten
    assert (await client.post(f"/admin/questions/{qids[0]}/tts", headers=A, json={"kind": "question"})).status_code == 409
    n = len(calls)
    r2 = await client.post(f"/admin/questions/{qids[0]}/tts", headers=A, json={"kind": "question", "overwrite": True})
    assert r2.status_code == 200 and r2.json()["file"] != r.json()["file"] and len(calls) == n + 1
    assert (await client.get(f"/files/{r.json()['file']}", headers=U)).status_code == 404   # the old clip is gone, no leak

    # bulk: only what is missing, never overwrites, counts failures, skips empty text
    await client.put(f"/admin/questions/{qids[3]}", headers=A, json={"course_id": cid, "number": 4, "text": "Q4?", "model_answer": ""})
    await client.put(f"/admin/questions/{qids[2]}", headers=A, json={"course_id": cid, "number": 3, "text": "Q3?", "model_answer": "A3"})
    calls.clear()
    j = (await client.post(f"/admin/courses/{cid}/tts-missing", headers=A, json={"lang": "uz"})).json()
    assert j["total"] == 6          # 8 possible clips, minus Q1's existing question audio, minus Q4's empty answer
    st = (await client.get(f"/admin/tts/jobs/{j['job_id']}", headers=A)).json()
    assert st["running"] is False and (st["done"], st["failed"]) == (5, 1) and st["last_error"] == "Azure refused the request"
    assert ("Q1?", "SECRET-KEY-1234", "westeurope", "uz-UZ-MadinaNeural") not in calls     # Q1 already had audio: untouched
    assert all(v == "uz-UZ-MadinaNeural" for *_, v in calls)
    done = {q["number"]: (q["question_audio"] is not None, q["answer_audio"] is not None)
            for q in (await client.get(f"/admin/courses/{cid}/questions", headers=A)).json()}
    assert done == {1: (True, True), 2: (True, True), 3: (True, False), 4: (True, False)}
    # running it again only retries what is still missing (the failed Q3 answer; Q4's answer has no text)
    calls.clear()
    j2 = (await client.post(f"/admin/courses/{cid}/tts-missing", headers=A, json={})).json()
    assert j2["total"] == 1 and [c[0] for c in calls] == ["A3"]

    # a bad key stops the batch at once instead of failing every clip
    async def rejected(text, **kw):
        calls.append(text)
        raise tts.TTSError("Azure rejected the key or region", fatal=True)

    monkeypatch.setattr(tts, "synthesize", rejected)
    cid2, _, _ = await seed_course(client, A, n=5)
    calls.clear()
    j3 = (await client.post(f"/admin/courses/{cid2}/tts-missing", headers=A, json={})).json()
    st3 = (await client.get(f"/admin/tts/jobs/{j3['job_id']}", headers=A)).json()
    assert len(calls) == 1 and st3["failed"] == 1 and st3["running"] is False and "rejected" in st3["last_error"]
    assert (await client.get("/admin/tts/jobs/9999", headers=A)).status_code == 404
    assert (await client.get("/admin/tts/status", headers=U)).status_code in (401, 403)

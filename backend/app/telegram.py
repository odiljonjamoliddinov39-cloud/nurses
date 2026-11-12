"""Telegram bot, run inside the backend through a webhook (no separate bot process).

- /start: welcome, ask for the phone number, then the "Open app" button.
- Contact: saved to the user (only their own contact).
- Admins get payment requests with the receipt and Approve / Reject buttons.
- Users get approval, rejection and expiry reminders.
"""
import hashlib
import json
import logging

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import Settings, get_settings
from .db import get_session
from .models import PaymentRequest, Plan, StoredFile, User
from .security import upsert_user
from .services import approve_payment, file_id, get_setting, reject_payment

log = logging.getLogger("uvicorn.error")
router = APIRouter(prefix="/telegram", tags=["telegram"])

T = {
    "welcome": {
        "uz": "Assalomu alaykum! Og'zaki imtihonga tayyorgarlik ilovasiga xush kelibsiz.\nDavom etish uchun telefon raqamingizni yuboring.",
        "ru": "Здравствуйте! Добро пожаловать в тренажёр устного экзамена.\nЧтобы продолжить, отправьте свой номер телефона.",
        "en": "Hello! Welcome to the oral exam trainer.\nPlease share your phone number to continue.",
    },
    "share": {"uz": "📱 Raqamni yuborish", "ru": "📱 Отправить номер", "en": "📱 Share phone number"},
    "thanks": {"uz": "Rahmat! Ilovani oching:", "ru": "Спасибо! Откройте приложение:", "en": "Thank you! Open the app:"},
    "open": {"uz": "Ilovani ochish", "ru": "Открыть приложение", "en": "Open app"},
    "no_app": {"uz": "Ilova hali sozlanmagan.", "ru": "Приложение ещё не настроено.", "en": "The app is not configured yet."},
    "approved": {
        "uz": "✅ To'lovingiz tasdiqlandi. Kirish {date} gacha ochiq.",
        "ru": "✅ Оплата подтверждена. Доступ открыт до {date}.",
        "en": "✅ Your payment is approved. Access is open until {date}.",
    },
    "rejected": {
        "uz": "❌ To'lov tasdiqlanmadi. Sabab: {reason}\nIlovada qayta chek yuborishingiz mumkin.",
        "ru": "❌ Оплата не подтверждена. Причина: {reason}\nВы можете отправить чек заново в приложении.",
        "en": "❌ Your payment was not approved. Reason: {reason}\nYou can send a new receipt in the app.",
    },
    "remind": {
        "uz": "⏰ Obunangiz {days} kundan keyin tugaydi ({date}). Ilovada uzaytirishingiz mumkin.",
        "ru": "⏰ Подписка закончится через {days} дн. ({date}). Продлить можно в приложении.",
        "en": "⏰ Your subscription ends in {days} day(s) ({date}). You can renew in the app.",
    },
    "expired": {
        "uz": "Obunangiz muddati tugadi. Davom etish uchun ilovada uzaytiring.",
        "ru": "Срок подписки истёк. Продлите её в приложении, чтобы продолжить.",
        "en": "Your subscription has ended. Renew it in the app to continue.",
    },
}

REJECT_REASONS = {
    "amount": {"uz": "summa noto'g'ri", "ru": "неверная сумма", "en": "wrong amount"},
    "unreadable": {"uz": "chek o'qib bo'lmaydi", "ru": "чек нечитаемый", "en": "receipt unreadable"},
    "notfound": {"uz": "to'lov topilmadi", "ru": "платёж не найден", "en": "payment not found"},
    "other": {"uz": "boshqa sabab", "ru": "другая причина", "en": "other"},
}


def tr(key: str, lang: str | None, **kw) -> str:
    d = T[key]
    return d.get(lang or "uz", d["uz"]).format(**kw)


def reason_text(code: str, lang: str | None) -> str:
    d = REJECT_REASONS.get(code)
    return d.get(lang or "uz", d["uz"]) if d else code


def webhook_secret(bot_token: str) -> str:
    return hashlib.sha256(("webhook:" + bot_token).encode()).hexdigest()[:48]


async def call(method: str, payload: dict | None = None, files: dict | None = None) -> dict | None:
    """Call the Bot API; never raises (notifications must not break the request that sent them)."""
    token = get_settings().bot_token
    if not token:
        return None
    url = f"https://api.telegram.org/bot{token}/{method}"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            if files:
                data = {k: (json.dumps(v) if isinstance(v, (dict, list)) else str(v))
                        for k, v in (payload or {}).items()}
                r = await client.post(url, data=data, files=files)
            else:
                r = await client.post(url, json=payload or {})
        body = r.json()
        if not body.get("ok"):
            log.warning("Telegram %s failed: %s", method, body.get("description"))
            return None
        return body.get("result")
    except Exception:
        log.exception("Telegram %s failed", method)
        return None


async def send(chat_id: int, text: str, **extra) -> None:
    await call("sendMessage", {"chat_id": chat_id, "text": text, **extra})


def open_app_markup(url: str, lang: str | None) -> dict:
    return {"inline_keyboard": [[{"text": tr("open", lang), "web_app": {"url": url}}]]}


async def setup_bot(public_base: str, miniapp_url: str) -> None:
    """Register the webhook and the chat menu button. Called on startup."""
    settings = get_settings()
    if not settings.bot_token or not public_base:
        return
    await call("setWebhook", {
        "url": f"{public_base}/telegram/webhook",
        "secret_token": webhook_secret(settings.bot_token),
        "allowed_updates": ["message", "callback_query"],
    })
    if miniapp_url.startswith("https://"):
        await call("setChatMenuButton", {"menu_button": {
            "type": "web_app", "text": "Ilova", "web_app": {"url": miniapp_url}}})


# ---------------------------------------------------------------- notifications

def payment_admin_markup(req_id: int) -> dict:
    return {"inline_keyboard": [[
        {"text": "✅ Approve", "callback_data": f"pay:a:{req_id}"},
        {"text": "❌ Reject", "callback_data": f"pay:r:{req_id}"},
    ]]}


def payment_caption(req: PaymentRequest, user: User, plan: Plan) -> str:
    return (f"💳 New payment request {req.payment_code}\n"
            f"Name: {user.full_name or '-'}\nPhone: {user.phone or '-'}\n"
            f"Telegram ID: {user.telegram_id}\nPlan: {plan.name} ({plan.days} days)\n"
            f"Amount: {req.amount:,} UZS".replace(",", " "))


async def notify_admins_payment(session: AsyncSession, req: PaymentRequest) -> None:
    settings = get_settings()
    user = await session.get(User, req.user_id)
    plan = await session.get(Plan, req.plan_id)
    if not user or not plan:
        return
    caption = payment_caption(req, user, plan)
    receipt = None
    fid = file_id(req.receipt_image)
    if fid:
        receipt = await session.get(StoredFile, fid)
    for admin in settings.admin_ids:
        if receipt and receipt.content_type.startswith("image/"):
            await call("sendPhoto", {"chat_id": admin, "caption": caption,
                                     "reply_markup": payment_admin_markup(req.id)},
                       files={"photo": ("receipt", receipt.data, receipt.content_type)})
        else:
            await send(admin, caption, reply_markup=payment_admin_markup(req.id))


async def notify_payment_result(user: User, approved: bool, *, ends_at=None, reason: str = "") -> None:
    if approved:
        await send(user.telegram_id, tr("approved", user.ui_language, date=ends_at.strftime("%d.%m.%Y")))
    else:
        await send(user.telegram_id, tr("rejected", user.ui_language, reason=reason_text(reason, user.ui_language)))


# ---------------------------------------------------------------- webhook

async def _edit_admin_message(cb: dict, suffix: str) -> None:
    msg = cb.get("message") or {}
    chat_id = (msg.get("chat") or {}).get("id")
    if not chat_id:
        return
    original = msg.get("caption") if "caption" in msg else msg.get("text", "")
    method = "editMessageCaption" if "caption" in msg or msg.get("photo") else "editMessageText"
    field = "caption" if method == "editMessageCaption" else "text"
    await call(method, {"chat_id": chat_id, "message_id": msg.get("message_id"),
                        field: f"{original}\n\n{suffix}", "reply_markup": {"inline_keyboard": []}})


async def handle_callback(session: AsyncSession, cb: dict) -> None:
    settings = get_settings()
    from_id = (cb.get("from") or {}).get("id")
    data = cb.get("data") or ""
    answer = {"callback_query_id": cb.get("id")}
    if from_id not in settings.admin_ids or not data.startswith("pay:"):
        await call("answerCallbackQuery", {**answer, "text": "Not allowed"})
        return
    parts = data.split(":")
    try:
        req_id = int(parts[2])
    except (IndexError, ValueError):
        return
    req = await session.get(PaymentRequest, req_id)
    if req is None:
        await call("answerCallbackQuery", {**answer, "text": "Request not found"})
        return
    action = parts[1]
    if action == "r":  # ask for the reason
        msg = cb.get("message") or {}
        rows = [[{"text": REJECT_REASONS[c]["en"], "callback_data": f"pay:x:{req_id}:{c}"}]
                for c in REJECT_REASONS]
        rows.append([{"text": "↩ Back", "callback_data": f"pay:b:{req_id}"}])
        await call("editMessageReplyMarkup", {"chat_id": msg["chat"]["id"], "message_id": msg["message_id"],
                                              "reply_markup": {"inline_keyboard": rows}})
        await call("answerCallbackQuery", answer)
        return
    if action == "b":
        msg = cb.get("message") or {}
        await call("editMessageReplyMarkup", {"chat_id": msg["chat"]["id"], "message_id": msg["message_id"],
                                              "reply_markup": payment_admin_markup(req_id)})
        await call("answerCallbackQuery", answer)
        return
    user = await session.get(User, req.user_id)
    try:
        if action == "a":
            sub = await approve_payment(session, req, from_id)
            await session.commit()
            await call("answerCallbackQuery", {**answer, "text": "Approved"})
            await _edit_admin_message(cb, f"✅ Approved, access until {sub.ends_at:%d.%m.%Y}")
            if user:
                await notify_payment_result(user, True, ends_at=sub.ends_at)
        elif action == "x":
            reason = parts[3] if len(parts) > 3 else "other"
            await reject_payment(session, req, from_id, reason)
            await session.commit()
            await call("answerCallbackQuery", {**answer, "text": "Rejected"})
            await _edit_admin_message(cb, f"❌ Rejected: {reason_text(reason, 'en')}")
            if user:
                await notify_payment_result(user, False, reason=reason)
    except HTTPException as exc:
        await call("answerCallbackQuery", {**answer, "text": str(exc.detail)})
        await _edit_admin_message(cb, f"ℹ️ {exc.detail}")


async def handle_message(session: AsyncSession, msg: dict) -> None:
    frm = msg.get("from") or {}
    chat_id = (msg.get("chat") or {}).get("id")
    if not frm.get("id") or not chat_id or (msg.get("chat") or {}).get("type") != "private":
        return
    full_name = " ".join(p for p in (frm.get("first_name"), frm.get("last_name")) if p) or None
    try:
        user = await upsert_user(session, frm["id"], full_name)
    except HTTPException:
        return  # blocked
    if not user.ui_language or user.ui_language not in ("uz", "ru", "en"):
        user.ui_language = "uz"
    lang = user.ui_language
    miniapp_url = await get_setting(session, "miniapp_url")

    async def offer_app(text: str):
        if miniapp_url.startswith("https://"):
            await send(chat_id, text, reply_markup=open_app_markup(miniapp_url, lang))
        else:
            await send(chat_id, f"{text}\n{tr('no_app', lang)}")

    contact = msg.get("contact")
    if contact:
        if contact.get("user_id") == frm["id"] and contact.get("phone_number"):
            user.phone = contact["phone_number"][:32]
            await session.commit()
        await send(chat_id, "✅", reply_markup={"remove_keyboard": True})
        await offer_app(tr("thanks", lang))
        return
    text = (msg.get("text") or "").strip()
    if text.startswith("/start") or not user.phone:
        welcome = (await get_setting(session, "welcome_text")) or tr("welcome", lang)
        if user.phone:
            await offer_app(welcome)
        else:
            await send(chat_id, welcome, reply_markup={
                "keyboard": [[{"text": tr("share", lang), "request_contact": True}]],
                "resize_keyboard": True, "one_time_keyboard": True})
        return
    await offer_app(tr("thanks", lang))


@router.post("/webhook")
async def webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str = Header(default=""),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    if not settings.bot_token or x_telegram_bot_api_secret_token != webhook_secret(settings.bot_token):
        raise HTTPException(403, "bad secret")
    update = await request.json()
    try:
        if "callback_query" in update:
            await handle_callback(session, update["callback_query"])
        elif "message" in update:
            await handle_message(session, update["message"])
    except Exception:
        log.exception("webhook update failed")
        await session.rollback()
    return {"ok": True}

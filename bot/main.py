"""Telegram bot: /start -> share contact -> open Mini App.
TODO: payment alerts to admin with Approve/Reject inline buttons, user notifications,
expiry reminders (3 and 1 day), broadcasts. All state lives in the backend API."""
import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton,
                           Message, ReplyKeyboardMarkup, WebAppInfo)
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    bot_token: str
    miniapp_url: str  # required: https URL of the deployed Mini App
    api_url: str = "http://backend:8000"


settings = Settings()
if not settings.miniapp_url.startswith("https://"):
    raise SystemExit("MINIAPP_URL must be the https URL of the deployed Mini App")
dp = Dispatcher()

OPEN_APP = InlineKeyboardMarkup(inline_keyboard=[[
    InlineKeyboardButton(text="Open app", web_app=WebAppInfo(url=settings.miniapp_url))
]])


@dp.message(CommandStart())
async def start(message: Message):
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Share contact", request_contact=True)]],
        resize_keyboard=True, one_time_keyboard=True)
    await message.answer("Welcome! Please share your phone number to continue.", reply_markup=kb)


@dp.message(F.contact)
async def got_contact(message: Message):
    # TODO: POST contact to backend (verify contact.user_id == message.from_user.id)
    await message.answer("Thank you! Tap below to open the app.", reply_markup=OPEN_APP)


async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(Bot(settings.bot_token))


if __name__ == "__main__":
    asyncio.run(main())

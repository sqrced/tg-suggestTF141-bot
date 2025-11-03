import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties
from fastapi import FastAPI, Request
from aiogram.webhook.aiohttp_server import SimpleRequestHandler
import asyncio

# Токен бота и ID админов / канала
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(",")))  # Пример: 123456,789012
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))  # ID канала, куда бот постит предложения

# --- НАСТРОЙКА БОТА ---
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# --- FASTAPI ДЛЯ РЕНДЕРА ---
app = FastAPI()

# Путь вебхука
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = os.getenv("RENDER_EXTERNAL_URL", "") + WEBHOOK_PATH

# Клавиатура для админов
def get_admin_kb(user_id, message_type, file_id=None, caption=None):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve|{user_id}|{message_type}|{file_id or 'none'}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject|{user_id}")
        ]
    ])
    return kb

# --- ОБРАБОТКА ПРЕДЛОЖЕНИЙ ---
@dp.message(F.text | F.photo | F.video | F.voice | F.document)
async def handle_proposal(message: types.Message):
    user_id = message.from_user.id
    text = message.caption or message.text or ""

    for admin_id in ADMIN_IDS:
        if message.photo:
            await bot.send_photo(
                admin_id,
                message.photo[-1].file_id,
                caption=f"📩 Новое предложение:\n\n{text}",
                reply_markup=get_admin_kb(user_id, "photo", message.photo[-1].file_id, text)
            )
        elif message.video:
            await bot.send_video(
                admin_id,
                message.video.file_id,
                caption=f"📩 Новое предложение:\n\n{text}",
                reply_markup=get_admin_kb(user_id, "video", message.video.file_id, text)
            )
        elif message.voice:
            await bot.send_voice(
                admin_id,
                message.voice.file_id,
                caption=f"📩 Новое голосовое предложение.",
                reply_markup=get_admin_kb(user_id, "voice", message.voice.file_id)
            )
        elif message.document:
            await bot.send_document(
                admin_id,
                message.document.file_id,
                caption=f"📩 Новое предложение:\n\n{text}",
                reply_markup=get_admin_kb(user_id, "document", message.document.file_id, text)
            )
        else:
            await bot.send_message(
                admin_id,
                f"📩 Новое предложение:\n\n{text}",
                reply_markup=get_admin_kb(user_id, "text")
            )

    await message.answer("✅ Ваше предложение отправлено на рассмотрение администраторам!")

# --- ОБРАБОТКА КНОПОК АДМИНА ---
@dp.callback_query(F.data.startswith("approve"))
async def approve_proposal(callback: types.CallbackQuery):
    _, user_id, msg_type, file_id = callback.data.split("|")
    user_id = int(user_id)

    if msg_type == "photo":
        await bot.send_photo(CHANNEL_ID, file_id, caption=callback.message.caption.split("\n\n", 1)[-1])
    elif msg_type == "video":
        await bot.send_video(CHANNEL_ID, file_id, caption=callback.message.caption.split("\n\n", 1)[-1])
    elif msg_type == "voice":
        await bot.send_voice(CHANNEL_ID, file_id)
    elif msg_type == "document":
        await bot.send_document(CHANNEL_ID, file_id, caption=callback.message.caption.split("\n\n", 1)[-1])
    else:
        text = callback.message.text.split("\n\n", 1)[-1]
        await bot.send_message(CHANNEL_ID, text)

    await bot.send_message(user_id, "🎉 Ваше предложение одобрено и опубликовано в канале!")
    await callback.message.edit_text("✅ Предложение одобрено и опубликовано!")

@dp.callback_query(F.data.startswith("reject"))
async def reject_proposal(callback: types.CallbackQuery):
    _, user_id = callback.data.split("|")
    user_id = int(user_id)
    await bot.send_message(user_id, "❌ Ваше предложение было отклонено администраторами.")
    await callback.message.edit_text("🚫 Предложение отклонено.")

# --- FASTAPI СЕРВЕР ДЛЯ РЕНДЕРА ---
@app.on_event("startup")
async def on_startup():
    await bot.set_webhook(WEBHOOK_URL)
    print("✅ Вебхук установлен:", WEBHOOK_URL)

@app.post(WEBHOOK_PATH)
async def webhook(request: Request):
    update = await request.json()
    await dp.feed_webhook_update(bot, update)
    return {"ok": True}

@app.on_event("shutdown")
async def on_shutdown():
    await bot.delete_webhook()

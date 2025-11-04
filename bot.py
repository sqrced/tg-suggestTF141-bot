import os
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, InputMediaVideo, InputMediaDocument
from aiohttp import web

# --- Настройки через переменные окружения ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS").split(",")))
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
PORT = int(os.getenv("PORT", 10000))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- Клавиатура модерации ---
def moderation_kb(user_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve:{user_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject:{user_id}")
        ]
    ])

# --- Хранилище временных предложений ---
pending_suggestions = {}  # {user_id: [types.Message, ...]}

# --- /start ---
@dp.message()
async def start_cmd(message: types.Message):
    if message.text and message.text.startswith("/start"):
        await message.answer(
            "Отправь своё предложение."
        )

# --- Обработка предложений ---
@dp.message()
async def handle_suggestion(message: types.Message):
    user_id = message.from_user.id
    if user_id not in pending_suggestions:
        pending_suggestions[user_id] = []
    pending_suggestions[user_id].append(message)

    await message.answer("🕙 Ваше предложение отправлено на рассмотрение модераторам.")

    caption = message.caption if hasattr(message, "caption") and message.caption else message.text if message.text else ""
    for admin_id in ADMIN_IDS:
        kb = moderation_kb(user_id)
        if message.content_type == "text":
            await bot.send_message(admin_id, f"Новое предложение от пользователя {user_id}:\n\n{caption}", reply_markup=kb)
        elif message.content_type == "photo":
            await bot.send_photo(admin_id, message.photo[-1].file_id, caption=caption, reply_markup=kb)
        elif message.content_type == "video":
            await bot.send_video(admin_id, message.video.file_id, caption=caption, reply_markup=kb)
        elif message.content_type == "document":
            await bot.send_document(admin_id, message.document.file_id, caption=caption, reply_markup=kb)
        elif message.content_type == "voice":
            await bot.send_voice(admin_id, message.voice.file_id, caption=caption, reply_markup=kb)

# --- Модерация ---
@dp.callback_query()
async def moderation_callback(call: types.CallbackQuery):
    action, user_id = call.data.split(":")
    user_id = int(user_id)
    messages = pending_suggestions.get(user_id, [])

    if not messages:
        await call.answer("Предложение не найдено или уже обработано.")
        return

    # --- Одобрение ---
    if action == "approve":
        media_group = []
        text_sent = False
        for msg in messages:
            if msg.content_type == "text" and not text_sent:
                await bot.send_message(CHANNEL_ID, msg.text)
                text

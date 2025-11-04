import os
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, InputMediaVideo, InputMediaDocument
from aiohttp import web

# --- Настройки через переменные окружения ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = os.getenv("ADMIN_IDS")
CHANNEL_ID = os.getenv("CHANNEL_ID")
PORT = int(os.getenv("PORT", 10000))

# --- Проверка переменных окружения ---
assert BOT_TOKEN, "❌ BOT_TOKEN не задан"
assert ADMIN_IDS, "❌ ADMIN_IDS не заданы"
assert CHANNEL_ID, "❌ CHANNEL_ID не задан"

ADMIN_IDS = list(map(int, ADMIN_IDS.split(",")))
CHANNEL_ID = int(CHANNEL_ID)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- Хранилище временных предложений ---
pending_suggestions = {}  # {user_id: [types.Message, ...]}

# --- Клавиатура модерации ---
def moderation_kb(user_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve:{user_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject:{user_id}")
        ]
    ])

# --- /start ---
@dp.message()
async def start_cmd(message: types.Message):
    if message.text and message.text.startswith("/start"):
        await message.answer(
            "Привет! Отправь своё предложение.")

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

    if action == "approve":
        media_group = []
        text_sent = False
        for msg in messages:
            if msg.content_type == "text" and not text_sent:
                await bot.send_message(CHANNEL_ID, msg.text)
                text_sent = True
            elif msg.content_type == "photo":
                media_group.append(InputMediaPhoto(media=msg.photo[-1].file_id, caption=msg.caption if msg.caption else None))
            elif msg.content_type == "video":
                media_group.append(InputMediaVideo(media=msg.video.file_id, caption=msg.caption if msg.caption else None))
            elif msg.content_type == "document":
                media_group.append(InputMediaDocument(media=msg.document.file_id, caption=msg.caption if msg.caption else None))
            elif msg.content_type == "voice":
                await bot.send_voice(CHANNEL_ID, msg.voice.file_id, caption=msg.caption if msg.caption else "")

        if media_group:
            await bot.send_media_group(CHANNEL_ID, media_group)

        await bot.send_message(user_id, "Ваше предложение одобрено и опубликовано!")
        pending_suggestions.pop(user_id, None)
        await call.message.edit_reply_markup(None)
        await call.answer("Вы одобрили предложение.")

    elif action == "reject":
        await bot.send_message(user_id, "К сожалению, ваше предложение отклонено.")
        pending_suggestions.pop(user_id, None)
        await call.message.edit_reply_markup(None)
        await call.answer("Вы отклонили предложение.")

# --- Webhook обработка ---
async def handle_webhook(request):
    update = types.Update(**await request.json())
    await dp.process_update(update)
    return web.Response()

app = web.Application()
app.router.add_post(f"/{BOT_TOKEN}", handle_webhook)

# --- Запуск приложения ---
if __name__ == "__main__":
    print("✅ Бот стартует через Webhook на Render")
    web.run_app(app, host="0.0.0.0", port=PORT)

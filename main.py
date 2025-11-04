import os
import logging
import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardButton, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiohttp import web

# === ЛОГИРОВАНИЕ ===
logging.basicConfig(level=logging.INFO)

# === ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMINS = os.getenv("ADMINS", "")
CHANNEL_ID = os.getenv("CHANNEL_ID")

if not BOT_TOKEN or not ADMINS or not CHANNEL_ID:
    raise ValueError("❌ Укажи BOT_TOKEN, ADMINS и CHANNEL_ID в переменных окружения Render!")

ADMIN_IDS = [int(x) for x in ADMINS.split(",") if x.strip().isdigit()]

# === ИНИЦИАЛИЗАЦИЯ БОТА ===
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# Временное хранилище предложений
user_suggestions = {}  # {message_id: user_id}


# === /start ===
@dp.message(Command("start"))
async def start_cmd(message: Message):
    await message.answer(
        "👋 Привет! Отправь сюда своё предложение."
    )


# === ОБРАБОТКА ПРЕДЛОЖЕНИЙ ===
@dp.message(F.content_type.in_({"text", "photo", "video", "document"}))
async def handle_suggestion(message: Message):
    kb = InlineKeyboardBuilder()
    kb.add(
        InlineKeyboardButton(text="✅ Одобрить", callback_data="approve"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data="decline")
    )

    caption = message.caption or message.text or ""
    suggestion_text = f"📩 Новое предложение от пользователя #{message.from_user.id}\n\n{caption}"

    for admin_id in ADMIN_IDS:
        sent = None
        if message.photo:
            sent = await bot.send_photo(admin_id, message.photo[-1].file_id, caption=suggestion_text, reply_markup=kb.as_markup())
        elif message.video:
            sent = await bot.send_video(admin_id, message.video.file_id, caption=suggestion_text, reply_markup=kb.as_markup())
        elif message.document:
            sent = await bot.send_document(admin_id, message.document.file_id, caption=suggestion_text, reply_markup=kb.as_markup())
        else:
            sent = await bot.send_message(admin_id, suggestion_text, reply_markup=kb.as_markup())

        if sent:
            user_suggestions[sent.message_id] = message.from_user.id

    await message.answer("🕙 Твоё предложение отправлено на модерацию!")


# === ОБРАБОТКА ОДОБРЕНИЯ/ОТКЛОНЕНИЯ ===
@dp.callback_query(F.data.in_({"approve", "decline"}))
async def handle_decision(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("⛔ Только админ может это делать.", show_alert=True)
        return

    suggestion_id = callback.message.message_id
    user_id = user_suggestions.get(suggestion_id)
    caption = callback.message.caption or callback.message.text or ""

    if callback.data == "approve":
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer("✅ Одобрено!")
        # Публикация в канал
        if callback.message.photo:
            await bot.send_photo(CHANNEL_ID, callback.message.photo[-1].file_id, caption=caption)
        elif callback.message.video:
            await bot.send_video(CHANNEL_ID, callback.message.video.file_id, caption=caption)
        elif callback.message.document:
            await bot.send_document(CHANNEL_ID, callback.message.document.file_id, caption=caption)
        else:
            await bot.send_message(CHANNEL_ID, caption)

        if user_id:
            await bot.send_message(user_id, "✅ Твоё предложение одобрено и опубликовано в канале!")

    elif callback.data == "decline":
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.answer("❌ Отклонено.")
        if user_id:
            await bot.send_message(user_id, "❌ Твоё предложение отклонено.")


# === ПРОСТОЙ ВЕБ-СЕРВЕР (для Render ping) ===
async def handle(request):
    return web.Response(text="Bot is alive!")

async def web_server():
    app = web.Application()
    app.router.add_get("/", handle)
    port = int(os.environ.get("PORT", 10000))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"🌐 Web server started on port {port}")


# === ЗАПУСК ВСЕГО ===
async def main():
    await asyncio.gather(
        web_server(),
        dp.start_polling(bot)
    )

if __name__ == "__main__":
    asyncio.run(main())

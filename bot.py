import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

# === НАСТРОЙКИ ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [955483416, 2025057922]  # твои ID
CHANNEL_ID = int(os.getenv("CHANNEL_ID", 0))  # ID канала
WEBHOOK_HOST = "https://tg-suggesttf141-bot.onrender.com"
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = WEBHOOK_HOST + WEBHOOK_PATH

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# === /start ===
@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    await message.answer("👋 Привет! Отправь своё предложение.")

# === Приём сообщений ===
@dp.message(F.content_type.in_(
    ["text", "photo", "video", "voice", "document", "animation"]
))
async def handle_suggestion(message: types.Message):
    user = message.from_user
    sender = f"👤 @{user.username or 'без_ника'} (ID: {user.id})"
    caption = message.caption or message.text or "(без текста)"
    text_to_send = f"💬 Предложение от {sender}:\n\n{caption}"

    # Кнопки для админов
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Одобрить", callback_data=f"approve_{user.id}")
    kb.button(text="❌ Отклонить", callback_data=f"decline_{user.id}")
    kb.adjust(2)

    # Отправляем контент админам
    for admin_id in ADMIN_IDS:
        try:
            if message.text:
                await bot.send_message(admin_id, text_to_send, reply_markup=kb.as_markup())
            elif message.photo:
                await bot.send_photo(admin_id, message.photo[-1].file_id, caption=text_to_send, reply_markup=kb.as_markup())
            elif message.video:
                await bot.send_video(admin_id, message.video.file_id, caption=text_to_send, reply_markup=kb.as_markup())
            elif message.voice:
                await bot.send_voice(admin_id, message.voice.file_id, caption=text_to_send, reply_markup=kb.as_markup())
            elif message.document:
                await bot.send_document(admin_id, message.document.file_id, caption=text_to_send, reply_markup=kb.as_markup())
            elif message.animation:
                await bot.send_animation(admin_id, message.animation.file_id, caption=text_to_send, reply_markup=kb.as_markup())
        except Exception as e:
            print(f"Ошибка при отправке админу {admin_id}: {e}")

    await message.answer("✅ Твоё предложение отправлено на рассмотрение администрации!")

# === Обработка кнопок от админов ===
@dp.callback_query(F.data.startswith("approve_"))
async def approve_post(callback: types.CallbackQuery):
    user_id = int(callback.data.split("_")[1])

    # Получаем оригинальное сообщение
    msg = callback.message
    content_type = msg.content_type

    # Публикуем в канал без приписок
    try:
        if content_type == "text":
            await bot.send_message(CHANNEL_ID, msg.text)
        elif content_type == "photo":
            await bot.send_photo(CHANNEL_ID, msg.photo[-1].file_id, caption=msg.caption)
        elif content_type == "video":
            await bot.send_video(CHANNEL_

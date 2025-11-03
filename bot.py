import os
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiohttp import web

# === НАСТРОЙКИ ===
BOT_TOKEN = os.getenv("BOT_TOKEN")  # токен хранится в Render → Environment
ADMIN_IDS = [955483416, 2025057922]  # твои ID админов
WEBHOOK_HOST = "https://tg-suggesttf141-bot.onrender.com"  # URL Render-проекта
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = WEBHOOK_HOST + WEBHOOK_PATH

# === НАСТРОЙКА БОТА ===
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# === ОБРАБОТЧИКИ ===
@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    await message.answer("👋 Привет! Отправь сообщение, и я передам его админам!")

@dp.message()
async def handle_message(message: types.Message):
    if message.from_user.id in ADMIN_IDS:
        await message.answer("👑 Принято, админ!")
    else:
        text = f"💬 Новое сообщение от @{message.from_user.username or 'без ника'}:\n\n{message.text}"
        for admin in ADMIN_IDS:
            try:
                await bot.send_message(admin, text)
            except Exception as e:
                print(f"Ошибка отправки админу {admin}: {e}")
        await message.answer("✅ Твоё сообщение отправлено администрации!")

# === WEBHOOK ЗАПУСК ===
async def on_startup(app):
    await bot.set_webhook(WEBHOOK_URL)
    print(f"Webhook установлен: {WEBHOOK_URL}")

async def on_shutdown(app):
    await bot.delete_webhook()
    await bot.session.close()
    print("Webhook удалён и сессия закрыта.")

app = web.Application()
app.on_startup.append(on_startup)
app.on_shutdown.append(on_shutdown)
app.router.add_post(WEBHOOK_PATH, dp.webhook_handler())

if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))

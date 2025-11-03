import os
import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

# === НАСТРОЙКИ ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [955483416, 2025057922]  # ID админов
GROUP_ID = int(os.getenv("GROUP_ID", 0))  # ID группы (из Render)
WEBHOOK_HOST = "https://tg-suggesttf141-bot.onrender.com"
WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = WEBHOOK_HOST + WEBHOOK_PATH

# === НАСТРОЙКА БОТА ===
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# === ОБРАБОТЧИКИ ===
@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    await message.answer("👋 Привет! Отправь сообщение, и я передам его админам и в группу!")

@dp.message()
async def handle_message(message: types.Message):
    if message.from_user.id in ADMIN_IDS:
        await message.answer("👑 Принято, админ!")
    else:
        text = f"💬 Предложение от @{message.from_user.username or 'без ника'}:\n\n{message.text}"
        
        # Отправляем админам
        for admin in ADMIN_IDS:
            try:
                await bot.send_message(admin, text)
            except Exception as e:
                print(f"Ошибка при отправке админу {admin}: {e}")
        
        # Отправляем в группу (если указана)
        if GROUP_ID != 0:
            try:
                await bot.send_message(GROUP_ID, text)
            except Exception as e:
                print(f"Ошибка при отправке в группу: {e}")

        await message.answer("✅ Твоё сообщение отправлено администрации!")

# === WEBHOOK ЗАПУСК ===
async def on_startup(app):
    await bot.set_webhook(WEBHOOK_URL)
    print(f"✅ Webhook установлен: {WEBHOOK_URL}")

async def on_shutdown(app):
    await bot.delete_webhook()
    await bot.session.close()
    print("❌ Webhook удалён и сессия закрыта.")

app = web.Application()

# Настраиваем webhook обработчик
SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=WEBHOOK_PATH)

# Привязываем события запуска/остановки
app.on_startup.append(on_startup)
app.on_shutdown.append(on_shutdown)
setup_application(app, dp, bot=bot)

if __name__ == "__main__":
    web.run_app(app, host="0.0.0.0", port=int(os.getenv("PORT", 8080)))

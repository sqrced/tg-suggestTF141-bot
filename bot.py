import os
import asyncio
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(CommandStart())
async def start(message: Message):
    await message.answer("👋 Привет! Отправь сюда предложение, и я передам его администраторам.")

@dp.message(F.text)
async def handle_suggestion(message: Message):
    text = message.text
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve:{message.from_user.id}:{text}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject:{message.from_user.id}")
        ]
    ])
    for admin_id in ADMIN_IDS:
        await bot.send_message(admin_id, f"📩 Новое предложение от @{message.from_user.username or 'без ника'}:\n\n{text}", reply_markup=kb)
    await message.reply("✅ Твое предложение отправлено на проверку!")

@dp.callback_query(F.data.startswith("approve"))
async def approve_callback(callback: types.CallbackQuery):
    _, user_id, text = callback.data.split(":", 2)
    await bot.send_message(CHANNEL_ID, f"✨ Новое предложение:\n\n{text}")
    await callback.message.edit_text("✅ Одобрено и опубликовано!")

@dp.callback_query(F.data.startswith("reject"))
async def reject_callback(callback: types.CallbackQuery):
    _, user_id = callback.data.split(":")
    await callback.message.edit_text("❌ Отклонено.")
    try:
        await bot.send_message(user_id, "❌ Твое предложение отклонено.")
    except:
        pass

async def main():
    print("🤖 Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

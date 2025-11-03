import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.utils.keyboard import InlineKeyboardBuilder
from fastapi import FastAPI, Request
import asyncio
import uvicorn

# === Переменные окружения ===
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMINS = [int(x) for x in os.getenv("ADMINS", "").split(",") if x]
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()
app = FastAPI()


# === Команда /start ===
@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    await message.answer(
        "👋 Привет! Отправь сюда своё предложение (текст, фото, видео, голос и т.п.).\n"
        "После проверки админами оно может попасть в канал анонимно 💬"
    )


# === Приём любого контента ===
@dp.message(F.content_type.in_({"text", "photo", "video", "voice", "document"}))
async def suggestion_handler(message: types.Message):
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_{message.chat.id}_{message.message_id}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"decline_{message.chat.id}_{message.message_id}")
            ]
        ]
    )

    # Отправка предложения всем админам
    for admin_id in ADMINS:
        caption = f"<b>Новое предложение от пользователя:</b>\n\n"
        if message.caption:
            caption += message.caption
        elif message.text:
            caption += message.text

        try:
            if message.photo:
                await bot.send_photo(admin_id, message.photo[-1].file_id, caption=caption, reply_markup=kb)
            elif message.video:
                await bot.send_video(admin_id, message.video.file_id, caption=caption, reply_markup=kb)
            elif message.voice:
                await bot.send_voice(admin_id, message.voice.file_id, caption=caption, reply_markup=kb)
            elif message.document:
                await bot.send_document(admin_id, message.document.file_id, caption=caption, reply_markup=kb)
            else:
                await bot.send_message(admin_id, caption, reply_markup=kb)
        except Exception as e:
            print(f"Ошибка при отправке админу {admin_id}: {e}")

    await message.answer("🕙 Твоё предложение отправлено на проверку.")


# === Обработка кнопок ===
@dp.callback_query(F.data.startswith(("approve_", "decline_")))
async def handle_decision(callback: types.CallbackQuery):
    data = callback.data.split("_")
    action, user_id, msg_id = data[0], int(data[1]), int(data[2])

    try:
        user_msg = await bot.forward_message(callback.from_user.id, user_id, msg_id)
    except Exception as e:
        await callback.message.answer(f"⚠️ Ошибка при обработке сообщения: {e}")
        return

    if action == "approve_":
        # Получаем оригинальное сообщение
        msg = await bot.copy_message(
            chat_id=CHANNEL_ID,
            from_chat_id=user_id,
            message_id=msg_id,
            caption=None
        )
        await callback.message.answer("✅ Предложение опубликовано в канал.")
        try:
            await bot.send_message(user_id, "✅ Твоё предложение одобрено и опубликовано анонимно!")
        except:
            pass
    else:
        await callback.message.answer("❌ Предложение отклонено.")
        try:
            await bot.send_message(user_id, "❌ К сожалению, твоё предложение отклонено.")
        except:
            pass

    await callback.answer()


# === Webhook маршруты для Render ===
@app.post("/")
async def webhook(request: Request):
    update = await request.json()
    await dp.feed_update(bot, update)
    return {"ok": True}


@app.on_event("startup")
async def on_startup():
    await bot.set_webhook(WEBHOOK_URL)
    print("✅ Webhook установлен!")


@app.on_event("shutdown")
async def on_shutdown():
    await bot.delete_webhook()
    print("🛑 Webhook удалён!")


# === Запуск (Render) ===
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("bot:app", host="0.0.0.0", port=port)

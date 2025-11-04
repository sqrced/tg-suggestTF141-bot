# main.py
import os
import asyncio
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Request
import aiosqlite
import uvicorn

from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ContentType

# --------------------------
# Настройки через переменные окружения
# --------------------------
TOKEN = os.getenv("TOKEN")  # токен бота
ADMIN_IDS = os.getenv("ADMIN_IDS", "")  # через запятую, например: "123456789,987654321"
CHANNEL_ID = os.getenv("CHANNEL_ID")  # например @your_channel или -1001234567890

if not TOKEN or not ADMIN_IDS or not CHANNEL_ID:
    raise RuntimeError("Пожалуйста, установи переменные окружения: TOKEN, ADMIN_IDS, CHANNEL_ID")

ADMIN_IDS = [int(x.strip()) for x in ADMIN_IDS.split(",") if x.strip()]
DB_PATH = os.getenv("DB_PATH", "proposals.db")

bot = Bot(token=TOKEN, parse_mode="HTML")
dp = Dispatcher()

app = FastAPI()
_polling_task: Optional[asyncio.Task] = None

# --------------------------
# Database helpers
# --------------------------
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS proposals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            from_chat_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL
        );
        """)
        await db.commit()

async def save_proposal(user_id: int, from_chat_id: int, message_id: int) -> int:
    created_at = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO proposals (user_id, from_chat_id, message_id, created_at) VALUES (?, ?, ?, ?)",
            (user_id, from_chat_id, message_id, created_at)
        )
        await db.commit()
        return cur.lastrowid

async def get_proposal(proposal_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT id, user_id, from_chat_id, message_id, status, created_at FROM proposals WHERE id = ?",
            (proposal_id,)
        )
        return await cur.fetchone()

async def update_proposal_status(proposal_id: int, status: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE proposals SET status = ? WHERE id = ?", (status, proposal_id))
        await db.commit()

# --------------------------
# UI helpers
# --------------------------
def moderation_keyboard(proposal_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve:{proposal_id}"),
                InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject:{proposal_id}")
            ]
        ]
    )

# --------------------------
# Handlers
# --------------------------
@dp.message.register(
    content_types=[
        ContentType.TEXT,
        ContentType.PHOTO,
        ContentType.VIDEO,
        ContentType.VOICE,
        ContentType.AUDIO,
        ContentType.DOCUMENT,
        ContentType.STICKER,
        ContentType.VIDEO_NOTE,
    ]
)
async def handle_user_message(message: types.Message):
    proposal_id = await save_proposal(
        user_id=message.from_user.id,
        from_chat_id=message.chat.id,
        message_id=message.message_id
    )

    preview_text = f"📌 Новое предложение #{proposal_id}\nТип: {message.content_type}\nВремя (UTC): {datetime.utcnow().isoformat()}"

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, preview_text)
            await message.copy_to(chat_id=admin_id, reply_markup=moderation_keyboard(proposal_id))
        except Exception as e:
            print(f"Ошибка отправки админу {admin_id}: {e}")

    await message.answer("🕙 Ваше предложение отправлено на рассмотрение модераторам (анонимно). Спасибо!")

@dp.callback_query.register(lambda c: c.data and (c.data.startswith("approve:") or c.data.startswith("reject:")))
async def handle_moderation_callback(callback: types.CallbackQuery):
    data = callback.data
    action, sid = data.split(":")
    proposal_id = int(sid)

    row = await get_proposal(proposal_id)
    if not row:
        await callback.answer("❗ Предложение не найдено", show_alert=True)
        return

    _, user_id, from_chat_id, message_id, status, _ = row

    if status != "pending":
        await callback.answer("Это предложение уже обработано.", show_alert=True)
        return

    if action == "approve":
        try:
            await bot.copy_message(chat_id=CHANNEL_ID, from_chat_id=from_chat_id, message_id=message_id)
        except Exception as e:
            await callback.answer("Ошибка при публикации в канал: " + str(e), show_alert=True)
            return

        await update_proposal_status(proposal_id, "approved")
        try:
            await bot.send_message(user_id, f"✅ Ваше предложение #{proposal_id} одобрено и опубликовано в канале.")
        except Exception:
            pass
        await callback.answer("✔️ Предложение одобрено и опубликовано.")
        try:
            await callback.message.edit_text(callback.message.text + "\n\n✅ Одобрено")
        except Exception:
            pass

    elif action == "reject":
        await update_proposal_status(proposal_id, "rejected")
        try:
            await bot.send_message(user_id, f"❌ Ваше предложение #{proposal_id} отклонено.")
        except Exception:
            pass
        await callback.answer("Предложение отклонено.")
        try:
            await callback.message.edit_text(callback.message.text + "\n\n❌ Отклонено")
        except Exception:
            pass

# --------------------------
# FastAPI endpoints
# --------------------------
@app.get("/")
async def root():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}

@app.post("/tg-webhook")
async def telegram_webhook(request: Request):
    update = types.Update(**await request.json())
    await dp.process_update(update)
    return {"ok": True}

# --------------------------
# Startup / Shutdown
# --------------------------
@app.on_event("startup")
async def on_startup():
    print("Startup: init DB and start polling")
    await init_db()
    global _polling_task
    loop = asyncio.get_event_loop()
    _polling_task = loop.create_task(dp.start_polling(bot, allowed_updates=types.AllowedUpdates.MESSAGE | types.AllowedUpdates.CALLBACK_QUERY))

@app.on_event("shutdown")
async def on_shutdown():
    print("Shutdown: stopping polling and closing bot")
    global _polling_task
    if _polling_task:
        _polling_task.cancel()
        try:
            await _polling_task
        except asyncio.CancelledError:
            pass
    await bot.session.close()

# --------------------------
# Run (локальный запуск)
# --------------------------
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)))

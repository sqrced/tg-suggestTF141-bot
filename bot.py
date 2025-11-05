import os
import logging
import aiosqlite
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from aiogram.filters import Command
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Конфигурация ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = os.getenv("ADMIN_IDS", "")
CHANNEL_ID = os.getenv("CHANNEL_ID")
WEBHOOK_BASE = os.getenv("WEBHOOK_BASE")
PORT = int(os.getenv("PORT", "8000"))

if not BOT_TOKEN or not ADMIN_IDS or not CHANNEL_ID or not WEBHOOK_BASE:
    raise SystemExit("❌ Укажи BOT_TOKEN, ADMIN_IDS, CHANNEL_ID и WEBHOOK_BASE в переменных окружения.")

ADMIN_IDS = [int(x.strip()) for x in ADMIN_IDS.split(",") if x.strip()]
CHANNEL_ID = int(CHANNEL_ID)

WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = WEBHOOK_BASE.rstrip("/") + WEBHOOK_PATH
DB_PATH = "proposals.db"

# --- Инициализация ---
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- База данных ---
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS proposals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                from_chat_id INTEGER NOT NULL,
                from_message_id INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL
            )
        """)
        await db.commit()

# --- Клавиатура для админов ---
def admin_keyboard(proposal_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve:{proposal_id}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject:{proposal_id}")
    ]])

# --- /start ---
@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.reply("Привет! Отправь мне своё предложение.")

# --- Приём предложений ---
@dp.message()
async def handle_proposal(message: Message):
    created_at = datetime.utcnow().isoformat()

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO proposals (user_id, from_chat_id, from_message_id, created_at) VALUES (?, ?, ?, ?)",
            (message.from_user.id, message.chat.id, message.message_id, created_at)
        )
        await db.commit()
        proposal_id = cur.lastrowid

    await message.reply("🕙 Ваше предложение отправлено на проверку модераторам.")

    for admin in ADMIN_IDS:
        try:
            await bot.forward_message(chat_id=admin, from_chat_id=message.chat.id, message_id=message.message_id)
            text = (
                f"Новая заявка #{proposal_id}\n"
                f"Отправитель: <a href='tg://user?id={message.from_user.id}'>{message.from_user.full_name}</a>\n"
                f"ID: <code>{message.from_user.id}</code>"
            )
            await bot.send_message(chat_id=admin, text=text, parse_mode="HTML", reply_markup=admin_keyboard(proposal_id))
        except Exception as e:
            logger.exception(f"Ошибка при уведомлении админа {admin}: {e}")

# --- Callback от админов ---
@dp.callback_query()
async def handle_admin_callback(query: CallbackQuery):
    await query.answer()  # чтобы Telegram не "висел"
    data = query.data

    if not data or (":" not in data):
        return

    action, sid = data.split(":", 1)
    if action not in ("approve", "reject"):
        return

    user_id = query.from_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("У вас нет прав на это.", show_alert=True)
        return

    try:
        proposal_id = int(sid)
    except ValueError:
        await query.answer("Неверный ID.")
        return

    async with aiosqlite.connect(DB_PATH) as db:
        row = await db.execute_fetchone(
            "SELECT id, user_id, from_chat_id, from_message_id, status FROM proposals WHERE id = ?",
            (proposal_id,)
        )

    if not row:
        await query.answer("Заявка не найдена.")
        return

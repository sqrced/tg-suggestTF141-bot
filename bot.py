# bot.py (полностью)
import os
import logging
import aiosqlite
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
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
def admin_keyboard(proposal_id: int) -> InlineKeyboardMarkup:
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

    # Ответ пользователю
    try:
        await message.reply("🕙 Ваше предложение отправлено на проверку модераторам.")
    except Exception:
        logger.warning("Не удалось ответить пользователю (возможно, закрыт чат).")

    # Уведомляем админов: форвардим оригинал и шлём сообщение с кнопками
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
# Используем универсальный хендлер для callback_query — фильтрация внутри функции.
@dp.callback_query()
async def handle_admin_callback(query: CallbackQuery):
    data = query.data or ""
    user_id = query.from_user.id

    # Игнорируем посторонние callback'и
    if not (data.startswith("approve:") or data.startswith("reject:")):
        # не отвечаем — это не наши кнопки
        return

    if user_id not in ADMIN_IDS:
        await query.answer("У вас нет прав на это действие.", show_alert=True)
        return

    action, sid = data.split(":", 1)
    try:
        proposal_id = int(sid)
    except ValueError:
        await query.answer("Неверный ID заявки.", show_alert=True)
        return

    # Получаем заявку из БД
    async with aiosqlite.connect(DB_PATH) as db:
        row = await db.execute_fetchone(
            "SELECT id, user_id, from_chat_id, from_message_id, status FROM proposals WHERE id = ?",
            (proposal_id,)
        )

    if not row:
        await query.answer("Заявка не найдена.", show_alert=True)
        return

    _, proposer_id, from_chat_id, from_message_id, status = row

    if status != "pending":
        await query.answer("Эта заявка уже обработана.", show_alert=True)
        try:
            await query.message.edit_text(f"Заявка #{proposal_id} — уже {status}.")
        except Exception:
            pass
        return

    if action == "approve":
        try:
            await bot.copy_message(chat_id=CHANNEL_ID, from_chat_id=from_chat_id, message_id=from_message_id)
            # уведомляем автора (если можно)
            try:
                await bot.send_message(chat_id=proposer_id, text="✅ Ваше предложение одобрено и опубликовано в канале.")
            except Exception:
                logger.warning("Не удалось уведомить автора (возможно, закрыл чат).")

            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("UPDATE proposals SET status = 'approved' WHERE id = ?", (proposal_id,))
                await db.commit()

            try:
                await query.message.edit_text(f"Заявка #{proposal_id} — ✅ ОДОБРЕНО")
            except Exception:
                pass
            await query.answer("Заявка одобрена.")
        except Exception as e:
            logger.exception(f"Ошибка при публикации в канал: {e}")
            await query.answer("Ошибка при публикации в канал. Проверь, что бот — админ канала.", show_alert=True)

    else:  # reject
        try:
            try:
                await bot.send_message(chat_id=proposer_id, text="❌ Ваше предложение отклонено модераторами.")
            except Exception:
                logger.warning("Не удалось уведомить автора об отклонении.")

            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("UPDATE proposals SET status = 'rejected' WHERE id = ?", (proposal_id,))
                await db.commit()

            try:
                await query.message.edit_text(f"Заявка #{proposal_id} — ❌ ОТКЛОНЕНО")
            except Exception:
                pass
            await query.answer("Заявка отклонена.")
        except Exception as e:
            logger.exception(f"Ошибка при отклонении: {e}")
            await query.answer("Ошибка при отклонении.", show_alert=True)

# --- Webhook handler (надежный: пробует корректно передать Update в диспетчер) ---
async def handle_webhook(request: web.Request):
    try:
        data = await request.json()
    except Exception as e:
        logger.exception(f"Ошибка чтения JSON из webhook: {e}")
        return web.Response(status=400, text="bad request")

    # Пытаемся превратить dict в types.Update
    try:
        update = types.Update(**data)
    except Exception as e:
        logger.exception(f"Ошибка создания types.Update: {e}")
        return web.Response(status=400, text="bad update")

    # Попытки передать апдейт в Dispatcher разными способами в зависимости от версии aiogram
    dispatched = False
    try:
        # В некоторых версиях: dp.feed_update(bot, update)
        await dp.feed_update(bot, update)
        dispatched = True
    except AttributeError:
        pass
    except Exception as e:
        # если метод есть, но бросил — логируем и продолжаем (возможно сработало)
        logger.exception(f"dp.feed_update raised: {e}")
        dispatched = True  # уже попыталось, не пытать дальше

    if not dispatched:
        try:
            # другой вариант: dp.process_update(update)
            await dp.process_update(update)
            dispatched = True
        except AttributeError:
            pass
        except Exception as e:
            logger.exception(f"dp.process_update raised: {e}")
            dispatched = True

    if not dispatched:
        try:
            # ещё вариант: dp.feed_update(update)
            await dp.feed_update(update)
            dispatched = True
        except Exception as e:
            logger.exception(f"final attempt to dispatch update failed: {e}")

    return web.Response(text="ok")

# --- Startup / Shutdown ---
async def on_startup(app):
    await init_db()
    try:
        await bot.set_webhook(WEBHOOK_URL)
        logger.info(f"Webhook установлен: {WEBHOOK_URL}")
    except Exception as e:
        logger.exception(f"Не удалось установить webhook: {e}")
    logger.info("База данных и webhook готовы.")

async def on_shutdown(app):
    try:
        await bot.delete_webhook()
    except Exception:
        pass
    await bot.session.close()
    logger.info("Бот остановлен.")

# --- App и запуск ---
app = web.Application()
app.router.add_post(WEBHOOK_PATH, handle_webhook)
app.on_startup.append(on_startup)
app.on_shutdown.append(on_shutdown)

if __name__ == "__main__":
    # port из env (Render задаёт PORT), fallback — 8000
    port = int(os.environ.get("PORT", PORT))
    web.run_app(app, host="0.0.0.0", port=port)

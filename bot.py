from aiohttp import web
from aiogram import Bot, Dispatcher, types
import os
import asyncio

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS").split(",")))
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
PORT = int(os.getenv("PORT", 10000))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

pending_suggestions = {}

def moderation_kb(user_id: int):
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [
            types.InlineKeyboardButton("✅ Одобрить", callback_data=f"approve:{user_id}"),
            types.InlineKeyboardButton("❌ Отклонить", callback_data=f"reject:{user_id}")
        ]
    ])

@dp.message()
async def handle_message(message: types.Message):
    user_id = message.from_user.id
    if user_id not in pending_suggestions:
        pending_suggestions[user_id] = []
    pending_suggestions[user_id].append(message)

    await message.answer("🕙 Ваше предложение отправлено на рассмотрение модераторам.")

    caption = message.caption if getattr(message, "caption", None) else message.text if message.text else ""
    for admin_id in ADMIN_IDS:
        kb = moderation_kb(user_id)
        try:
            if message.content_type == "text":
                await bot.send_message(admin_id, caption, reply_markup=kb)
            elif message.content_type == "photo":
                await bot.send_photo(admin_id, message.photo[-1].file_id, caption=caption, reply_markup=kb)
            elif message.content_type == "video":
                await bot.send_video(admin_id, message.video.file_id, caption=caption, reply_markup=kb)
            elif message.content_type == "document":
                await bot.send_document(admin_id, message.document.file_id, caption=caption, reply_markup=kb)
            elif message.content_type == "voice":
                await bot.send_voice(admin_id, message.voice.file_id, caption=caption, reply_markup=kb)
        except Exception as e:
            print(f"Ошибка при отправке администратору {admin_id}: {e}")

@dp.callback_query()
async def handle_callback(call: types.CallbackQuery):
    action, user_id = call.data.split(":")
    user_id = int(user_id)
    messages = pending_suggestions.get(user_id, [])

    if not messages:
        await call.answer("Предложение не найдено или уже обработано.", show_alert=True)
        return

    try:
        if action == "approve":
            media_group = []
            text_sent = False
            for msg in messages:
                if msg.content_type == "text" and not text_sent:
                    await bot.send_message(CHANNEL_ID, msg.text)
                    text_sent = True
                elif msg.content_type == "photo":
                    media_group.append(types.InputMediaPhoto(media=msg.photo[-1].file_id, caption=msg.caption if msg.caption else None))
                elif msg.content_type == "video":
                    media_group.append(types.InputMediaVideo(media=msg.video.file_id, caption=msg.caption if msg.caption else None))
                elif msg.content_type == "document":
                    media_group.append(types.InputMediaDocument(media=msg.document.file_id, caption=msg.caption if msg.caption else None))
                elif msg.content_type == "voice":
                    await bot.send_voice(CHANNEL_ID, msg.voice.file_id, caption=msg.caption if msg.caption else "")

            if media_group:
                await bot.send_media_group(CHANNEL_ID, media_group)

            await bot.send_message(user_id, "✅ Ваше предложение одобрено и опубликовано!")
            pending_suggestions.pop(user_id, None)
            await call.message.edit_reply_markup(None)
            await call.answer("Предложение одобрено.")
        elif action == "reject":
            await bot.send_message(user_id, "❌ К сожалению, ваше предложение отклонено.")
            pending_suggestions.pop(user_id, None)
            await call.message.edit_reply_markup(None)
            await call.answer("Предложение отклонено.")
    except Exception as e:
        print(f"Ошибка при модерации предложения {user_id}: {e}")
        await call.answer("Произошла ошибка при обработке предложения.", show_alert=True)

# --- Webhook ---
async def handle_webhook(request):
    try:
        data = await request.json()
        print("Incoming update:", data)
        update = types.Update(**data)
        await dp.process_update(update)
    except Exception as e:
        print("Ошибка при обработке update:", e)
    finally:
        # Обязательный ответ Telegram
        return web.Response(text="ok")

app = web.Application()
app.router.add_post(f"/{BOT_TOKEN}", handle_webhook)

if __name__ == "__main__":
    print("✅ Бот стартует через Webhook")
    web.run_app(app, host="0.0.0.0", port=PORT)

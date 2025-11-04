from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
import os

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(i) for i in os.getenv("ADMIN_IDS").split(",")]
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

def approve_keyboard(caption, file_id=None, type_=None):
    buttons = [
        types.InlineKeyboardButton("✅ Одобрить", callback_data=f"approve|{type_}|{file_id}|{caption}"),
        types.InlineKeyboardButton("❌ Отклонить", callback_data="reject")
    ]
    return types.InlineKeyboardMarkup().add(*buttons)

@dp.message_handler(content_types=["text", "photo", "video"])
async def suggest(message: types.Message):
    caption = message.caption or message.text or ""
    user = f"@{message.from_user.username}" if message.from_user.username else message.from_user.full_name
    for admin in ADMIN_IDS:
        if message.photo:
            file_id = message.photo[-1].file_id
            await bot.send_photo(admin, file_id, caption=f"📩 От {user}:\n\n{caption}", reply_markup=approve_keyboard(caption, file_id, "photo"))
        elif message.video:
            file_id = message.video.file_id
            await bot.send_video(admin, file_id, caption=f"📩 От {user}:\n\n{caption}", reply_markup=approve_keyboard(caption, file_id, "video"))
        else:
            await bot.send_message(admin, f"📩 От {user}:\n\n{caption}", reply_markup=approve_keyboard(caption))
    await message.reply("🕙 Предложка отправлена на проверку!")

@dp.callback_query_handler(lambda c: c.data.startswith("approve"))
async def approve(callback: types.CallbackQuery):
    _, type_, file_id, caption = callback.data.split("|", 3)
    if type_ == "photo":
        await bot.send_photo(CHANNEL_ID, file_id, caption=caption)
    elif type_ == "video":
        await bot.send_video(CHANNEL_ID, file_id, caption=caption)
    else:
        await bot.send_message(CHANNEL_ID, caption)
    await callback.message.edit_text("✅ Пост опубликован!")
    await callback.answer("✅ Опубликовано!")

@dp.callback_query_handler(lambda c: c.data == "reject")
async def reject(callback: types.CallbackQuery):
    await callback.message.edit_text("❌ Предложка отклонена.")
    await callback.answer("❌ Отклонено")

if __name__ == "__main__":
    print("🤖 Бот запущен...")
    executor.start_polling(dp, skip_updates=True)

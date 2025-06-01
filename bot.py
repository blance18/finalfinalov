import logging
import sqlite3
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InputMediaPhoto, InputMediaVideo
from aiogram.dispatcher.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import asyncio
import os
from datetime import datetime, timedelta

API_TOKEN = 'YOUR_BOT_API_TOKEN'
PASSWORD = 'Hgirflazz18oq.'
AUTHORIZED_USERS = {6258371389}  # Уже добавленный Telegram ID

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

db_path = 'database/user.db'
os.makedirs('database', exist_ok=True)
conn = sqlite3.connect(db_path)
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS channels (chat_id TEXT)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id TEXT,
    text TEXT,
    media TEXT,
    buttons TEXT,
    time TEXT,
    repeat INTEGER
)''')
conn.commit()

user_states = {}

@dp.message_handler(commands=['start'])
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    cursor.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    if cursor.fetchone():
        await message.answer("Добро пожаловать в пост-бота!")
    else:
        await message.answer("🔐 Введите пароль:")
        user_states[user_id] = 'awaiting_password'

@dp.message_handler(lambda message: user_states.get(message.from_user.id) == 'awaiting_password')
async def password_check(message: types.Message):
    if message.text == PASSWORD:
        user_id = message.from_user.id
        cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        user_states.pop(user_id)
        await message.answer("✅ Пароль принят. Вы авторизованы!")
    else:
        await message.answer("❌ Неверный пароль. Попробуйте снова.")

@dp.message_handler(commands=['addchannel'])
async def add_channel(message: types.Message):
    user_id = message.from_user.id
    if not is_authorized(user_id):
        return await message.answer("❌ Доступ запрещён")
    await message.answer("🔗 Вставь ссылку на канал или chat_id:")
    user_states[user_id] = 'awaiting_channel'

@dp.message_handler(lambda message: user_states.get(message.from_user.id) == 'awaiting_channel')
async def save_channel(message: types.Message):
    user_states.pop(message.from_user.id)
    cursor.execute("INSERT INTO channels (chat_id) VALUES (?)", (message.text,))
    conn.commit()
    await message.answer("✅ Канал добавлен!")

def is_authorized(user_id):
    cursor.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    return cursor.fetchone() is not None or user_id in AUTHORIZED_USERS

@dp.message_handler(commands=['newpost'])
async def new_post(message: types.Message):
    if not is_authorized(message.from_user.id):
        return await message.answer("❌ Доступ запрещён")

    cursor.execute("SELECT chat_id FROM channels")
    channels = cursor.fetchall()
    if not channels:
        return await message.answer("Сначала добавьте канал через /addchannel")

    markup = InlineKeyboardMarkup()
    for ch in channels:
        markup.add(InlineKeyboardButton(ch[0], callback_data=f"channel:{ch[0]}"))
    await message.answer("📢 Выбери канал:", reply_markup=markup)
    user_states[message.from_user.id] = {'step': 'selecting_channel'}

@dp.callback_query_handler(lambda c: c.data.startswith("channel:"))
async def selected_channel(callback_query: types.CallbackQuery):
    channel = callback_query.data.split(":")[1]
    user_id = callback_query.from_user.id
    user_states[user_id] = {'channel': channel, 'step': 'waiting_text'}
    await bot.send_message(user_id, "✏️ Введи текст поста (или отправь . чтобы пропустить):")

@dp.message_handler(lambda msg: isinstance(user_states.get(msg.from_user.id), dict) and user_states[msg.from_user.id]['step'] == 'waiting_text')
async def post_text(msg: types.Message):
    user_id = msg.from_user.id
    user_states[user_id]['text'] = None if msg.text == '.' else msg.text
    user_states[user_id]['step'] = 'waiting_media'
    await msg.answer("📎 Отправь медиа (фото, видео, gif) или . чтобы пропустить:")

@dp.message_handler(content_types=types.ContentType.ANY)
async def handle_media_and_buttons(msg: types.Message):
    state = user_states.get(msg.from_user.id)
    if not isinstance(state, dict): return

    if state['step'] == 'waiting_media':
        if msg.content_type in [types.ContentType.PHOTO, types.ContentType.VIDEO, types.ContentType.ANIMATION]:
            file_id = msg.photo[-1].file_id if msg.photo else (msg.video.file_id if msg.video else msg.animation.file_id)
            user_states[msg.from_user.id]['media'] = file_id
        else:
            user_states[msg.from_user.id]['media'] = None if msg.text == '.' else None
        user_states[msg.from_user.id]['step'] = 'waiting_buttons'
        return await msg.answer("🔘 Введи до 3 кнопок в формате `Текст - ссылка`, каждая с новой строки, или . чтобы пропустить:")

    if state['step'] == 'waiting_buttons':
        buttons = []
        if msg.text != '.':
            for line in msg.text.splitlines():
                if '-' in line:
                    parts = line.split('-', 1)
                    buttons.append({'text': parts[0].strip(), 'url': parts[1].strip()})
        user_states[msg.from_user.id]['buttons'] = buttons
        user_states[msg.from_user.id]['step'] = 'waiting_schedule'
        await msg.answer("⏰ Введи время публикации в формате `DD.MM.YYYY HH:MM`:")

    elif state['step'] == 'waiting_schedule':
        try:
            dt = datetime.strptime(msg.text, "%d.%m.%Y %H:%M")
            user_states[msg.from_user.id]['time'] = dt
            user_states[msg.from_user.id]['step'] = 'waiting_repeat'
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🔁 Ежедневно", callback_data="repeat:yes"))
            markup.add(InlineKeyboardButton("📅 Один раз", callback_data="repeat:no"))
            await msg.answer("🔄 Повторять публикацию?", reply_markup=markup)
        except:
            await msg.answer("❌ Неверный формат времени. Используй `DD.MM.YYYY HH:MM`")

@dp.callback_query_handler(lambda c: c.data.startswith("repeat:"))
async def finish_post(callback_query: types.CallbackQuery):
    repeat = 1 if callback_query.data == "repeat:yes" else 0
    user_id = callback_query.from_user.id
    state = user_states.pop(user_id)
    cursor.execute("INSERT INTO posts (chat_id, text, media, buttons, time, repeat) VALUES (?, ?, ?, ?, ?, ?)", (
        state['channel'],
        state.get('text'),
        state.get('media'),
        str(state.get('buttons')),
        state['time'].strftime("%Y-%m-%d %H:%M:%S"),
        repeat
    ))
    conn.commit()
    await bot.send_message(user_id, "✅ Пост запланирован!")

async def scheduler():
    while True:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("SELECT * FROM posts WHERE time<=?", (now,))
        for post in cursor.fetchall():
            try:
                markup = InlineKeyboardMarkup()
                buttons = eval(post[4]) if post[4] else []
                for btn in buttons[:3]:
                    markup.add(InlineKeyboardButton(btn['text'], url=btn['url']))

                if post[3]:  # media
                    await bot.send_photo(chat_id=post[1], photo=post[3], caption=post[2], reply_markup=markup)
                else:
                    await bot.send_message(chat_id=post[1], text=post[2], reply_markup=markup)
            except Exception as e:
                print(f"Error sending post: {e}")
            if post[5]:  # repeat
                next_time = datetime.strptime(post[5], "%Y-%m-%d %H:%M:%S") + timedelta(days=1)
                cursor.execute("UPDATE posts SET time=? WHERE id=?", (next_time.strftime("%Y-%m-%d %H:%M:%S"), post[0]))
            else:
                cursor.execute("DELETE FROM posts WHERE id=?", (post[0],))
        conn.commit()
        await asyncio.sleep(60)

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.create_task(scheduler())
    executor.start_polling(dp, skip_updates=True)

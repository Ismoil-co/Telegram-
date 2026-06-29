import asyncio
import sqlite3
import os  # Модуль для безопасного чтения ключей из настроек сервера
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
# Используем стабильную библиотеку, которая работает с твоим типом ключа
import google.generativeai as genai 

# ==========================================
# ⚙️ БЛОК КОНФИГУРАЦИИ (БЕЗОПАСНЫЙ)
# ==========================================
# Бот автоматически возьмет ключи из панели управления Render
BOT_TOKEN = os.getenv("BOT_TOKEN", "СЮДА_НИЧЕГО_НЕ_ПИШИ")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "СЮДА_НИЧЕГО_НЕ_ПИШИ")

# Публичные ссылки (их скрывать не нужно)
CHANNEL_ID = "@ismoil_lab" 
CHANNEL_URL = "https://t.me/ismoil_lab"
ADMIN_ID = 8082255890  # Твой Telegram ID цифрами

# Настраиваем ИИ полученным ключом
genai.configure(api_key=GEMINI_API_KEY)

# ==========================================
# 🤖 ИНИЦИАЛИЗАЦИЯ БОТА
# ==========================================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Хранилище для истории диалогов ИИ (чтобы бот помнил контекст)
user_chats = {}

class AdminStates(StatesGroup):
    mailing_text = State()

# ==========================================
# 💾 БАЗА ДАННЫХ (SQLite)
# ==========================================
def init_db():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            join_date DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def add_user(user_id: int, username: str):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
    conn.commit()
    conn.close()

def get_users_count():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(user_id) FROM users")
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_all_users():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = [row[0] for row in cursor.fetchall()]
    conn.close()
    return users

# ==========================================
# 📢 ПРОВЕРКА ПОДПИСКИ НА КАНАЛ
# ==========================================
async def check_subscription(user_id: int) -> bool:
    if user_id == ADMIN_ID:
        return True
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        if member.status in ["member", "administrator", "creator"]:
            return True
        return False
    except Exception:
        return False

def get_sub_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Подписаться на канал", url=CHANNEL_URL)],
        [InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check_sub")]
    ])

# ==========================================
# 🚀 ОБРАБОТЧИКИ КОМАНД
# ==========================================
@dp.message(CommandStart())
async def start_cmd(message: Message):
    add_user(message.from_user.id, message.from_user.username)
    
    is_sub = await check_subscription(message.from_user.id)
    if is_sub:
        await message.answer(
            f"👋 Привет, {message.from_user.first_name}!\n\n"
            "Я твой профессиональный AI-помощник на базе **Gemini**.\n"
            "Я отлично помню контекст нашего диалога. Задавай любой вопрос!"
        )
    else:
        await message.answer(
            f"👋 Привет, {message.from_user.first_name}!\n\n"
            "Чтобы активировать нейросеть и начать пользоваться ботом, пожалуйста, подпишись на наш официальный канал.",
            reply_markup=get_sub_keyboard()
        )

@dp.callback_query(F.data == "check_sub")
async def callback_check_sub(callback: CallbackQuery):
    is_sub = await check_subscription(callback.from_user.id)
    if is_sub:
        await callback.message.edit_text("✨ Отлично! Доступ к ИИ открыт. Напиши свой первый вопрос!")
        await callback.answer()
    else:
        await callback.answer("❌ Ты всё еще не подписался на канал!", show_alert=True)

# ==========================================
# ⚙️ ПАНЕЛЬ АДМИНИСТРАТОРА
# ==========================================
@dp.message(Command("admin"))
async def admin_panel(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    count = get_users_count()
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Сделать рассылку", callback_data="admin_mail")]
    ])
    await message.answer(f"⚙️ **Панель администратора**\n\nВсего пользователей в базе: `{count}`", reply_markup=keyboard)

@dp.callback_query(F.data == "admin_mail")
async def admin_mail_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        return
    await callback.message.answer("📝 Введи текст для рассылки всем пользователям бота:")
    await state.set_state(AdminStates.mailing_text)
    await callback.answer()

@dp.message(AdminStates.mailing_text)
async def admin_mail_send(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    await state.clear()
    users = get_all_users()
    sent_count = 0
    
    status_msg = await message.answer("🚀 Рассылка запущена...")
    
    for user_id in users:
        try:
            await bot.send_message(chat_id=user_id, text=message.text)
            sent_count += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass
            
    await status_msg.edit_text(f"✅ Рассылка завершена!\nУспешно доставлено: {sent_count}/{len(users)}")

# ==========================================
# 🧠 ОБРАБОТКА ИИ (GEMINI)
# ==========================================
@dp.message(F.text)
async def handle_ai_message(message: Message):
    is_sub = await check_subscription(message.from_user.id)
    if not is_sub:
        await message.answer("⚠️ Доступ ограничен. Подпишись на канал.", reply_markup=get_sub_keyboard())
        return

    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    user_id = message.from_user.id
    
    # Инициализируем чат по правилам старой библиотеки для поддержки твоего ключа
    if user_id not in user_chats:
        try:
            user_chats[user_id] = genai.GenerativeModel('gemini-pro').start_chat(history=[])
        except Exception as model_e:
            print(f"Ошибка создания модели: {model_e}")

    try:
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, 
            lambda: user_chats[user_id].send_message(message.text)
        )
        await message.answer(response.text)
    except Exception as e:
        await message.answer("Произошла ошибка при генерации ответа. Попробуй еще раз.")
        print(f"Ошибка Gemini: {e}")

# ==========================================
# ПОТОК ЗАПУСКА
# ==========================================
async def main():
    init_db()
    print("ИИ-бот успешно запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

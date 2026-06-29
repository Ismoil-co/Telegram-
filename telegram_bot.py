import asyncio
import sqlite3
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from google import genai

# ==========================================
# ⚙️ БЛОК КОНФИГУРАЦИИ (ЗАПОЛНИ СВОИ ДАННЫЕ)
# ==========================================
BOT_TOKEN = "8920352441:AAF6zY_myN2Ezt816N2L9Y_IYk0yAaEQwyU"
GEMINI_API_KEY = "AQ.Ab8RN6I0X1dOpq3Yt9x8bozAW_JPESWyauKf1q85wV2isvRcAA"
CHANNEL_ID = "@ismoil_lab" 
CHANNEL_URL = "https://t.me/ismoil_lab"
ADMIN_ID = 8082255890  # Вставь свой Telegram ID цифрами

# ==========================================
# 🤖 ИНИЦИАЛИЗАЦИЯ
# ==========================================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
ai_client = genai.Client(api_key=GEMINI_API_KEY)

# Хранилище активных чатов Gemini для каждого пользователя
user_chats = {}

# Состояния для админ-панели
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
# 📢 ПРОВЕРКА ПОДПИСКИ
# ==========================================
async def check_subscription(user_id: int) -> bool:
    if user_id == ADMIN_ID:  # Админу проверку делать не обязательно
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
            "Я твой профессиональный AI-помощник на базе **Gemini 2.5**.\n"
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
            await asyncio.sleep(0.05)  # Защита от лимитов Telegram
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

    # Запускаем анимацию "печатает..."
    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    user_id = message.from_user.id
    
    # Если у пользователя еще нет сессии чата, создаем её
    if user_id not in user_chats:
        user_chats[user_id] = ai_client.chats.create(model='gemini-2.5-flash')

    try:
        # Отправляем сообщение в чат через executor, чтобы бот не зависал
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
# RUN BOT
# ==========================================
async def main():
    init_db()  # Инициализация базы данных
    print("Профессиональный ИИ-бот запущен и работает без ошибок!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
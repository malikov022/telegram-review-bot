# bot.py - Главный файл бота
import asyncio
import logging
from datetime import datetime, timedelta
import sqlite3
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice
import matplotlib
matplotlib.use('Agg')  # Важно для сервера
import matplotlib.pyplot as plt
import io

# ==================== НАСТРОЙКИ ====================
# Вставьте сюда ваш токен от BotFather
import os

BOT_TOKEN = os.getenv("BOT_TOKEN")

# ID админа (ваш Telegram ID) - узнаем позже
ADMIN_ID = 0

logging.basicConfig(level=logging.INFO)

# ==================== БАЗА ДАННЫХ ====================
DATABASE = "bot_data.db"

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            tariff TEXT DEFAULT 'free',
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP,
            payment_id TEXT
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usage_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            analysis_date DATE DEFAULT CURRENT_DATE,
            count INTEGER DEFAULT 0,
            UNIQUE(user_id, analysis_date)
        )
    """)
    
    conn.commit()
    conn.close()

def register_user(user_id, username=None, first_name=None):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO users (user_id, username, first_name)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            username = excluded.username,
            first_name = excluded.first_name
    """, (user_id, username, first_name))
    conn.commit()
    conn.close()

def get_user_tariff(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT tariff, expires_at FROM subscriptions 
        WHERE user_id = ? AND expires_at > ?
    """, (user_id, datetime.now()))
    result = cursor.fetchone()
    conn.close()
    return result['tariff'] if result else 'free'

def get_daily_limit(tariff):
    limits = {'free': 1, 'basic': 10, 'premium': 999}
    return limits.get(tariff, 1)

def check_and_increment_usage(user_id):
    tariff = get_user_tariff(user_id)
    limit = get_daily_limit(tariff)
    today = datetime.now().date()
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT OR IGNORE INTO usage_log (user_id, analysis_date, count)
        VALUES (?, ?, 0)
    """, (user_id, today))
    
    cursor.execute("""
        SELECT count FROM usage_log 
        WHERE user_id = ? AND analysis_date = ?
    """, (user_id, today))
    
    current_count = cursor.fetchone()['count']
    
    if current_count >= limit:
        conn.close()
        if tariff == 'free':
            return False, "❌ Лимит исчерпан (1 анализ/день).\n\n⭐ Basic — 10/день — 99₽\n🚀 Premium — безлимит — 299₽\n\n/subscribe — подключить"
        else:
            return False, f"❌ Лимит исчерпан ({limit}/день).\n\n🔄 Обновится завтра.\n🚀 Premium — безлимит: /subscribe"
    
    cursor.execute("""
        UPDATE usage_log SET count = count + 1 
        WHERE user_id = ? AND analysis_date = ?
    """, (user_id, today))
    conn.commit()
    conn.close()
    
    remaining = limit - current_count - 1
    if remaining == 0 and tariff == 'free':
        return True, "✅ Анализ запущен! Бесплатный лимит на сегодня исчерпан. /subscribe"
    elif tariff == 'premium':
        return True, f"✅ Анализ запущен! ♾️ Безлимит"
    else:
        return True, f"✅ Анализ запущен! Осталось сегодня: {remaining}"

def upgrade_subscription(user_id, tariff, days=30):
    expires = datetime.now() + timedelta(days=days)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO subscriptions (user_id, tariff, expires_at, payment_id)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            tariff = excluded.tariff,
            expires_at = excluded.expires_at,
            started_at = CURRENT_TIMESTAMP
    """, (user_id, tariff, expires, f"test_{datetime.now().timestamp()}"))
    conn.commit()
    conn.close()

# ==================== БОТ ====================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Тарифы
TARIFFS = {
    'basic': {'price': 9900, 'name': '⭐ Basic — 10 анализов/день', 'desc': '• 10 анализов в сутки\n• Приоритетная обработка\n• История 30 дней'},
    'premium': {'price': 29900, 'name': '🚀 Premium — Безлимит', 'desc': '• ♾️ Безлимитные анализы\n• Мгновенная обработка\n• Экспорт PDF/Excel\n• VIP поддержка'}
}

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    register_user(message.from_user.id, message.from_user.username, message.from_user.first_name)
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Basic — 99₽/мес", callback_data="pay_basic")],
        [InlineKeyboardButton(text="🚀 Premium — 299₽/мес", callback_data="pay_premium")],
        [InlineKeyboardButton(text="📊 Сравнить тарифы", callback_data="compare_tariffs")]
    ])
    
    await message.answer(
        "👋 <b>Привет! Я Review Insight Analyzer</b>\n\n"
        "🔍 Отправьте мне ссылку на бизнес:\n"
        "• 2GIS • Яндекс.Карты • Google Maps\n"
        "• Avito • Ozon\n\n"
        "📊 Я проанализирую отзывы и покажу:\n"
        "✅ Тональность отзывов\n"
        "✅ Ключевые темы\n"
        "✅ AI-рекомендации\n\n"
        "🆓 <b>Бесплатно:</b> 1 анализ в день\n"
        "⭐ <b>Basic:</b> 10 анализов/день — 99₽\n"
        "🚀 <b>Premium:</b> Безлимит — 299₽",
        parse_mode="HTML",
        reply_markup=keyboard
    )

@dp.message(Command("subscribe"))
async def cmd_subscribe(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Basic — 99₽/мес", callback_data="pay_basic")],
        [InlineKeyboardButton(text="🚀 Premium — 299₽/мес", callback_data="pay_premium")]
    ])
    
    await message.answer(
        "💎 <b>Выберите тариф:</b>\n\n"
        "⭐ <b>Basic — 99₽/мес</b>\n"
        "• 10 анализов в сутки\n"
        "• Приоритетная обработка\n"
        "• История до 30 дней\n\n"
        "🚀 <b>Premium — 299₽/мес</b>\n"
        "• ♾️ Безлимитные анализы\n"
        "• Мгновенная обработка\n"
        "• Экспорт PDF/Excel\n"
        "• VIP поддержка",
        parse_mode="HTML",
        reply_markup=keyboard
    )

@dp.message(Command("me"))
async def cmd_me(message: types.Message):
    user_id = message.from_user.id
    tariff = get_user_tariff(user_id)
    limit = get_daily_limit(tariff)
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT count FROM usage_log WHERE user_id = ? AND analysis_date = ?", (user_id, datetime.now().date()))
    result = cursor.fetchone()
    used = result['count'] if result else 0
    conn.close()
    
    tariff_names = {'free': '🆓 Free', 'basic': '⭐ Basic', 'premium': '🚀 Premium'}
    
    text = f"👤 <b>Ваш профиль:</b>\n\n"
    text += f"📛 Тариф: {tariff_names.get(tariff, 'Free')}\n"
    
    if limit < 999:
        text += f"📊 Использовано: {used}/{limit}\n"
        text += f"🔄 Осталось: {max(0, limit - used)}\n"
    else:
        text += f"📊 Анализов сегодня: {used} ♾️\n"
    
    text += f"\n/subscribe — изменить тариф\n/help — справка"
    
    await message.answer(text, parse_mode="HTML")

@dp.message(Command("help"))
async def cmd_help(message: types.Message):
    await message.answer(
        "📚 <b>Справка:</b>\n\n"
        "/start — главное меню\n"
        "/subscribe — тарифы\n"
        "/me — мой профиль\n"
        "/help — эта справка\n\n"
        "💡 Отправьте ссылку на бизнес для анализа!"
    )

@dp.callback_query(F.data == "compare_tariffs")
async def show_comparison(callback: types.CallbackQuery):
    text = (
        "📊 <b>Сравнение тарифов:</b>\n\n"
        "│ Функция          │ Free │ Basic │ Premium │\n"
        "│─────────────────│──────│───────│─────────│\n"
        "│ Анализов/день   │  1   │  10   │   ♾️    │\n"
        "│ Скорость        │ 🐌   │  ⚡   │   🚀    │\n"
        "│ История         │  -   │ 30 дн │  безл.  │\n"
        "│ Экспорт         │  -   │  PDF  │ PDF+XLS │\n"
        "│ Цена            │  0₽  │  99₽  │  299₽   │"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_tariffs")]
    ])
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data == "back_to_tariffs")
async def back_to_tariffs(callback: types.CallbackQuery):
    await cmd_subscribe(callback.message)
    await callback.answer()

@dp.callback_query(F.data.startswith("pay_"))
async def start_payment(callback: types.CallbackQuery):
    tariff = callback.data.split('_')[1]
    tariff_data = TARIFFS[tariff]
    
    # ДЛЯ ТЕСТА — сразу активируем подписку
    # В продакшене здесь будет платёж
    user_id = callback.from_user.id
    upgrade_subscription(user_id, tariff, 30)
    
    await callback.message.answer(
        f"🎉 <b>Оплата прошла успешно!</b>\n\n"
        f"Тариф: {tariff_data['name']}\n"
        f"📅 Действует 30 дней\n\n"
        f"Теперь у вас больше анализов! 🚀\n"
        f"Напишите /me чтобы проверить.",
        parse_mode="HTML"
    )
    await callback.answer()

@dp.message(F.text.contains("http"))
async def handle_url(message: types.Message):
    user_id = message.from_user.id
    register_user(user_id, message.from_user.username, message.from_user.first_name)
    
    # Проверка лимита
    allowed, status_message = check_and_increment_usage(user_id)
    if not allowed:
        await message.answer(status_message, parse_mode="HTML")
        return
    
    # Показываем статус
    await message.answer(status_message, parse_mode="HTML")
    
    # Имитация анализа (2 секунды)
    await asyncio.sleep(2)
    
    # Mock-данные
    import random
    pos = random.randint(70, 90)
    neg = random.randint(5, 20)
    neu = 100 - pos - neg
    score = round(4 + random.random(), 1)
    total = random.randint(50, 300)
    
    # Генерация графика
    plt.figure(figsize=(5, 5))
    plt.pie([pos, neg, neu], labels=['Позитив', 'Негатив', 'Нейтраль'], 
            colors=['#10B981', '#EF4444', '#9CA3AF'], autopct='%1.1f%%')
    plt.title("Тональность отзывов")
    
    buf = io.BytesIO()
    plt.savefig(buf, format='PNG', bbox_inches='tight')
    buf.seek(0)
    plt.close()
    
    # Отчёт
    report = (
        f"📊 <b>Результаты анализа</b>\n\n"
        f"⭐ Рейтинг: {score}/5.0\n"
        f"📝 Отзывов: {total}\n\n"
        f"🥧 <b>Тональность:</b>\n"
        f"🟢 Положительные: {pos}%\n"
        f"🔴 Отрицательные: {neg}%\n"
        f"⚪ Нейтральные: {neu}%\n\n"
        f"✅ <b>Сильные стороны:</b>\n"
        f"• Вежливый персонал\n"
        f"• Быстрое обслуживание\n\n"
        f"⚠️ <b>Риски:</b>\n"
        f"• Долгий ответ поддержки\n"
        f"• Цены выше средних"
    )
    
    await message.answer_photo(photo=buf, caption=report, parse_mode="HTML")
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Ещё анализ", callback_data="restart")],
        [InlineKeyboardButton(text="⭐ Расширить лимит", callback_data="pay_basic")]
    ])
    await message.answer("Что дальше?", reply_markup=keyboard)

@dp.callback_query(F.data == "restart")
async def restart(callback: types.CallbackQuery):
    await callback.message.answer("👋 Отправьте новую ссылку для анализа!")
    await callback.answer()

# ==================== ЗАПУСК ====================
async def main():
    init_db()
    print("✅ Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

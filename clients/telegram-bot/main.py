import os
import logging
import re
import httpx
from datetime import datetime, timedelta
from typing import Dict

from telegram import (
    Update, 
    InlineKeyboardButton, 
    InlineKeyboardMarkup, 
    ReplyKeyboardMarkup, 
    KeyboardButton
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    filters,
    ContextTypes
)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация из переменных окружения
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
API_GATEWAY_URL = os.getenv('API_GATEWAY_URL', 'http://api-gateway:8000')

# Состояния диалога
WAITING_FOR_REPO, WAITING_FOR_PERIOD = range(2)

# --- Вспомогательные функции ---

def get_main_menu():
    """Создает клавиатуру главного меню"""
    keyboard = [
        [KeyboardButton("🔍 Анализ репозитория")],
        [KeyboardButton("📜 История запросов"), KeyboardButton("📖 Помощь")],
        [KeyboardButton("🤖 О боте")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def call_api(endpoint: str, method: str = "GET", json_data: Dict = None):
    """Асинхронный вызов вашего API Gateway"""
    url = f"{API_GATEWAY_URL}{endpoint}"
    async with httpx.AsyncClient(timeout=180.0) as client:
        try:
            if method == "GET":
                response = await client.get(url)
            else:
                response = await client.post(url, json=json_data)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Ошибка при вызове API {url}: {e}")
            return None

# --- Обработчики команд и кнопок меню ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /start и кнопка Помощь"""
    await update.message.reply_text(
        "👋 Привет! Я бот для аналитики GitHub.\n\n"
        "Я могу проанализировать активность в репозитории и запросить "
        "рекомендации по улучшению проекта у **Mistral AI**.",
        reply_markup=get_main_menu(),
        parse_mode="Markdown"
    )

async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Кнопка О боте"""
    await update.message.reply_text(
        "🤖 *GitHub Analytics Bot*\n\n"
        "• **Стек:** Python, Telegram API, Microservices\n"
        "• **Интеллект:** Mistral AI\n"
        "• **Функции:** Анализ коммитов, статистика авторов, советы по коду.",
        parse_mode="Markdown"
    )

async def history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Кнопка История запросов"""
    await update.message.reply_text("⏳ Загружаю последние запросы...")
    data = await call_api("/api/history?limit=5")
    
    if not data or not data.get('history'):
        await update.message.reply_text("История запросов пока пуста.")
        return
    
    text = "📜 *Последние проанализированные проекты:*\n\n"
    for rec in data['history']:
        text += f"• `{rec['owner']}/{rec['repo_name']}`\n  └ Коммитов: {rec.get('total_commits', 0)}\n"
    
    await update.message.reply_text(text, parse_mode="Markdown")

# --- Логика анализа (Conversation) ---

async def analyze_init(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало процесса анализа"""
    await update.message.reply_text(
        "🔍 Введите путь к репозиторию в формате `owner/repo`.\n"
        "Пример: `facebook/react` или `python/cpython`",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup([[KeyboardButton("❌ Отмена")]], resize_keyboard=True)
    )
    return WAITING_FOR_REPO

async def receive_repo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Получение имени репозитория и проверка через API"""
    repo_input = update.message.text.strip()
    
    if repo_input == "❌ Отмена":
        await update.message.reply_text("Действие отменено.", reply_markup=get_main_menu())
        return ConversationHandler.END

    if not re.match(r'^[\w\-\.]+/[\w\-\.]+$', repo_input):
        await update.message.reply_text("❌ Неверный формат! Попробуйте еще раз (owner/repo):")
        return WAITING_FOR_REPO
    
    owner, repo = repo_input.split('/')
    context.user_data.update({"owner": owner, "repo": repo})
    
    await update.message.reply_text(f"⏳ Проверяю доступность `{repo_input}`...", parse_mode="Markdown")
    data = await call_api(f"/api/repo/{owner}/{repo}")
    
    if not data or not data.get('success'):
        await update.message.reply_text("❌ Репозиторий не найден или недоступен. Проверьте имя:")
        return WAITING_FOR_REPO

    keyboard = [
        [InlineKeyboardButton("📅 30 дней", callback_data="30"),
         InlineKeyboardButton("📅 90 дней", callback_data="90")],
        [InlineKeyboardButton("📅 Весь год", callback_data="365")]
    ]
    await update.message.reply_text(
        f"✅ Репозиторий найден: *{data['repo_info']['full_name']}*\n"
        f"Выберите период для анализа данных и генерации советов Mistral:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return WAITING_FOR_PERIOD

async def receive_period(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запуск глубокого анализа с вызовом Mistral"""
    query = update.callback_query
    await query.answer()
    
    days = int(query.data)
    owner = context.user_data['owner']
    repo = context.user_data['repo']
    
    await query.edit_message_text(
        f"🔄 Начинаю анализ `{owner}/{repo}` за {days} дней...\n"
        f"🤖 Опрашиваю **Mistral AI** для подготовки рекомендаций. Пожалуйста, подождите.",
        parse_mode="Markdown"
    )
    
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    
    # Отправляем запрос на шлюз, который дернет сервис аналитики
    data = await call_api("/api/analyze", method="POST", json_data={
        "owner": owner,
        "repo_name": repo,
        "start_date": start_date.isoformat() + "Z",
        "end_date": end_date.isoformat() + "Z"
    })
    
    if not data or not data.get('success'):
        await query.message.reply_text("❌ Произошла ошибка при анализе данных.", reply_markup=get_main_menu())
        return ConversationHandler.END

    # Сборка итогового сообщения
    stats = data.get('commit_stats', {})
    res = f"📊 *ИТОГИ АНАЛИЗА: {owner}/{repo}*\n"
    res += f"━━━━━━━━━━━━━━━━━━━━\n"
    res += f"💾 Всего коммитов: `{stats.get('total_commits', 0)}`\n"
    res += f"👥 Активных авторов: `{data.get('total_contributors', 0)}`\n"
    
    # Вывод рекомендаций Mistral (если сервис их прислал)
    mistral_rec = data.get('ai_recommendations') or data.get('ai_summary')
    if mistral_rec:
        res += f"\n💡 *РЕКОМЕНДАЦИИ MISTRAL AI:*\n{mistral_rec}"
    else:
        res += f"\n⚠️ Рекомендации от нейросети временно недоступны."

    # Отправка (с защитой от слишком длинных сообщений)
    if len(res) > 4096:
        for i in range(0, len(res), 4000):
            await query.message.reply_text(res[i:i+4000], parse_mode="Markdown")
    else:
        await query.message.reply_text(res, parse_mode="Markdown")
    
    await query.message.reply_text("Чем еще я могу помочь?", reply_markup=get_main_menu())
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сброс любого состояния"""
    await update.message.reply_text("Действие отменено.", reply_markup=get_main_menu())
    return ConversationHandler.END

# --- Запуск бота ---

def main():
    if not TELEGRAM_BOT_TOKEN:
        logger.error("Ошибка: TELEGRAM_BOT_TOKEN не задан!")
        return

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Настройка диалогового обработчика
    conv_handler = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex("^🔍 Анализ репозитория$"), analyze_init),
            CommandHandler("analyze", analyze_init)
        ],
        states={
            WAITING_FOR_REPO: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_repo)
            ],
            WAITING_FOR_PERIOD: [
                CallbackQueryHandler(receive_period)
            ],
        },
        fallbacks=[
            MessageHandler(filters.Regex("^❌ Отмена$"), cancel),
            CommandHandler("cancel", cancel)
        ],
        allow_reentry=True
    )
    
    # Регистрация обычных обработчиков
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.Regex("^📜 История запросов$"), history))
    app.add_handler(MessageHandler(filters.Regex("^🤖 О боте$"), about))
    app.add_handler(MessageHandler(filters.Regex("^📖 Помощь$"), start))
    
    # Добавляем диалог
    app.add_handler(conv_handler)
    
    logger.info("Бот запущен. Ожидание сообщений...")
    app.run_polling()

if __name__ == "__main__":
    main()
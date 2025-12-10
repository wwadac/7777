import logging
import sqlite3
import os
import shutil
from datetime import datetime
from typing import Dict, List
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from telegram.ext import (
    Application, 
    CommandHandler, 
    MessageHandler, 
    CallbackQueryHandler, 
    ContextTypes, 
    ConversationHandler,
    filters
)

# ========== КОНФИГУРАЦИЯ ==========
TOKEN = "8534057742:AAFfm2gswdz-b6STcrWcCdRfaToRDkPUu0A"
ADMIN_IDS = [6893832048]  # Только ваш ID
DB_FILE = "info.db"
BACKUP_DIR = "backups"
LOG_FILE = "bot.log"

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ========== БАЗА ДАННЫХ ==========
def init_db():
    """Инициализация базы данных."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS info (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            info_text TEXT NOT NULL,
            added_by INTEGER NOT NULL,
            added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_username ON info(username)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_id ON info(user_id)')
    
    conn.commit()
    conn.close()

def cleanup_database():
    """Очистка базы данных от старых записей."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM info WHERE added_date < datetime('now', '-30 days')")
        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()
        return deleted_count
    except Exception as e:
        logger.error(f"Ошибка при очистке БД: {e}")
        return 0

def backup_database():
    """Создание резервной копии базы данных."""
    try:
        if not os.path.exists(BACKUP_DIR):
            os.makedirs(BACKUP_DIR)
        timestamp = int(datetime.now().timestamp())
        backup_file = f"{BACKUP_DIR}/info.db.backup_{timestamp}"
        shutil.copy2(DB_FILE, backup_file)
        return backup_file
    except Exception as e:
        logger.error(f"Ошибка при создании бэкапа: {e}")
        return None

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def is_owner(user_id: int) -> bool:
    """Проверяет, является ли пользователь владельцем."""
    return user_id in ADMIN_IDS

def get_all_users():
    """Получает список всех пользователей."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT username FROM info ORDER BY username")
        users = [row[0] for row in cursor.fetchall()]
        conn.close()
        return users
    except Exception as e:
        logger.error(f"Ошибка при получении пользователей: {e}")
        return []

def get_user_info(username: str):
    """Получает информацию о пользователе."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT info_text, added_date FROM info WHERE username = ? ORDER BY added_date DESC",
            (username,)
        )
        info = cursor.fetchall()
        conn.close()
        return info
    except Exception as e:
        logger.error(f"Ошибка при получении информации: {e}")
        return []

def add_user_info(username: str, info_text: str, added_by: int):
    """Добавляет информацию о пользователе."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO info (user_id, username, info_text, added_by) VALUES (0, ?, ?, ?)",
            (username, info_text, added_by)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Ошибка при добавлении информации: {e}")
        return False

def delete_user_info(username: str):
    """Удаляет информацию о пользователе."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM info WHERE username = ?", (username,))
        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()
        return deleted_count > 0
    except Exception as e:
        logger.error(f"Ошибка при удалении информации: {e}")
        return False

# ========== ФУНКЦИИ ПАГИНАЦИИ ==========
def create_pagination_keyboard(users: List[str], current_page: int) -> InlineKeyboardMarkup:
    """Создает клавиатуру пагинации для списка пользователей."""
    items_per_page = 10
    total_pages = (len(users) + items_per_page - 1) // items_per_page
    
    keyboard = []
    
    # Кнопки навигации
    nav_buttons = []
    
    # Кнопка "В начало" (только если не на первой странице)
    if current_page > 0:
        nav_buttons.append(InlineKeyboardButton("⏮️ В начало", callback_data=f'page_0'))
    
    # Кнопка "Назад"
    if current_page > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ Назад", callback_data=f'page_{current_page-1}'))
    
    # Информация о странице
    info_button = InlineKeyboardButton(f"📄 {current_page+1}/{total_pages}", callback_data="noop")
    nav_buttons.append(info_button)
    
    # Кнопка "Вперед"
    if current_page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("Вперед ▶️", callback_data=f'page_{current_page+1}'))
    
    # Кнопка "В конец" (только если не на последней странице)
    if current_page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("В конец ⏭️", callback_data=f'page_{total_pages-1}'))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # Кнопка "Назад в меню"
    keyboard.append([InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')])
    
    return InlineKeyboardMarkup(keyboard)

def get_paginated_users(users: List[str], page: int = 0, items_per_page: int = 10) -> tuple:
    """Возвращает пользователей для конкретной страницы."""
    start_idx = page * items_per_page
    end_idx = min(start_idx + items_per_page, len(users))
    return users[start_idx:end_idx], len(users)

# ========== КЛАВИАТУРЫ ==========
def get_main_menu_keyboard():
    """Клавиатура главного меню."""
    keyboard = [
        [InlineKeyboardButton("📝 Добавить информацию", callback_data='add_info')],
        [InlineKeyboardButton("🗑️ Удалить информацию", callback_data='delete_info')],
        [InlineKeyboardButton("🔍 Найти информацию", callback_data='search_info')],
        [InlineKeyboardButton("📋 Весь список", callback_data='all_info')],
        [InlineKeyboardButton("⚙️ Управление БД", callback_data='db_management')]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_db_management_keyboard():
    """Клавиатура управления БД (только для владельца)."""
    keyboard = [
        [InlineKeyboardButton("💾 Создать бэкап", callback_data='create_backup')],
        [InlineKeyboardButton("🔄 Импорт БД", callback_data='import_db')],
        [InlineKeyboardButton("📊 Статистика", callback_data='stats')],
        [InlineKeyboardButton("🧹 Очистка", callback_data='cleanup')],
        [InlineKeyboardButton("🔙 Назад", callback_data='back_to_main')]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_back_keyboard():
    """Кнопка возврата."""
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='back_to_main')]]
    return InlineKeyboardMarkup(keyboard)

# ========== ОБРАБОТЧИКИ КОМАНД ==========
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start."""
    await update.message.reply_text(
        "🎮 *Информационный Бот*\n\n"
        "✨ *Возможности:*\n"
        "• 📝 Добавление информации о пользователях\n"
        "• 🔍 Поиск и просмотр информации\n"
        "• 🗑️ Управление записями\n"
        "• 💾 Резервное копирование (для владельца)\n\n"
        "👇 Используйте кнопки ниже для навигации:",
        parse_mode='Markdown',
        reply_markup=get_main_menu_keyboard()
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help."""
    help_text = (
        "🎮 *Информационный Бот - Справка*\n\n"
        "✨ *Основные команды:*\n"
        "`/start` - Запустить бота\n"
        "`/help` - Эта справка\n"
        "`/tops` - Весь список информации\n\n"
        "📝 *Работа с информацией:*\n"
        "`!инфо username` - Найти информацию\n"
        "`+инфо username текст` - Добавить информацию\n"
        "`-инфо username` - Удалить информацию\n\n"
        "⚙️ *Управление БД (владелец):*\n"
        "`/stats` - Статистика\n"
        "`/backup` - Создать бэкап\n"
        "`/cleanup` - Очистка\n\n"
        "💾 *Импорт БД:*\n"
        "Отправьте файл `info.db` в чат"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def tops_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /tops."""
    await show_all_info(update, context)

# ========== ОБНОВЛЕННЫЕ ФУНКЦИИ ПАГИНАЦИИ ==========
async def show_all_info_callback(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE):
    """Показывает всю информацию с пагинацией (через callback)."""
    users = get_all_users()
    
    if not users:
        await query.edit_message_text(
            "📭 *База данных пуста*\n\n"
            "Добавьте информацию с помощью кнопки ниже:",
            parse_mode='Markdown',
            reply_markup=get_main_menu_keyboard()
        )
        return
    
    context.user_data['all_users'] = users
    context.user_data['current_page'] = 0
    
    await show_page(query, context)

async def show_page(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE):
    """Показывает страницу со списком пользователей с полной навигацией."""
    users = context.user_data.get('all_users', [])
    current_page = context.user_data.get('current_page', 0)
    items_per_page = 10
    
    page_users, total_users = get_paginated_users(users, current_page, items_per_page)
    total_pages = (total_users + items_per_page - 1) // items_per_page
    
    if not page_users:
        await query.edit_message_text(
            "📭 *На этой странице нет данных*",
            parse_mode='Markdown',
            reply_markup=get_back_keyboard()
        )
        return
    
    message = f"📋 *Весь список информации*\n"
    message += f"Страница {current_page + 1} из {total_pages}\n"
    message += f"Всего пользователей: {total_users}\n\n"
    
    for username in page_users:
        info_list = get_user_info(username)
        if info_list:
            # Убираем @ чтобы не упоминать пользователей
            message += f"👤 *{username}*\n"
            for j, (text, date) in enumerate(info_list[:3], 1):
                date_str = datetime.strptime(date, '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y')
                message += f"  {j}. {text} ({date_str})\n"
            message += "\n"
    
    # Создаем клавиатуру пагинации с полной навигацией
    reply_markup = create_pagination_keyboard(users, current_page)
    
    await query.edit_message_text(message, parse_mode='Markdown', reply_markup=reply_markup)

async def page_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик переключения страниц."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if data == "noop":
        return
    
    page_num = int(data.split('_')[1])
    context.user_data['current_page'] = page_num
    
    await show_page(query, context)

async def show_all_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает всю информацию с пагинацией."""
    users = get_all_users()
    
    if not users:
        await update.message.reply_text(
            "📭 *База данных пуста*",
            parse_mode='Markdown'
        )
        return
    
    context.user_data['all_users'] = users
    context.user_data['current_page'] = 0
    
    # Для обычного сообщения создаем начальную страницу
    current_page = 0
    items_per_page = 10
    page_users, total_users = get_paginated_users(users, current_page, items_per_page)
    total_pages = (total_users + items_per_page - 1) // items_per_page
    
    message = f"📋 *Весь список информации*\n"
    message += f"Страница {current_page + 1} из {total_pages}\n"
    message += f"Всего пользователей: {total_users}\n\n"
    
    for username in page_users:
        info_list = get_user_info(username)
        if info_list:
            # Убираем @ чтобы не упоминать пользователей
            message += f"👤 *{username}*\n"
            for j, (text, date) in enumerate(info_list[:3], 1):
                date_str = datetime.strptime(date, '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y')
                message += f"  {j}. {text} ({date_str})\n"
            message += "\n"
    
    # Создаем клавиатуру пагинации
    reply_markup = create_pagination_keyboard(users, current_page)
    
    await update.message.reply_text(message, parse_mode='Markdown', reply_markup=reply_markup)

# ========== ОБРАБОТЧИКИ СООБЩЕНИЙ (УБРАНЫ УПОМИНАНИЯ) ==========
async def handle_info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик !инфо ник (без упоминания)."""
    try:
        text = update.message.text.strip()
        
        if not text.startswith('!инфо '):
            return
        
        parts = text.split(' ', 1)
        if len(parts) < 2:
            await update.message.reply_text("❌ Формат: `!инфо username`", parse_mode='Markdown')
            return
        
        username = parts[1].strip().lstrip('@')  # Убираем @ если есть
        if not username:
            await update.message.reply_text("❌ Укажите username", parse_mode='Markdown')
            return
        
        info_list = get_user_info(username)
        
        if not info_list:
            await update.message.reply_text(
                f"ℹ️ Информация о {username} не найдена.",
                parse_mode='Markdown'
            )
            return
        
        response = f"📋 *Информация о {username}:*\n\n"
        
        for i, (text, date) in enumerate(info_list, 1):
            date_str = datetime.strptime(date, '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y %H:%M')
            response += f"{i}. {text}\n   📅 {date_str}\n\n"
        
        await update.message.reply_text(response, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Ошибка поиска: {e}")
        await update.message.reply_text("❌ Ошибка при поиске информации")

async def handle_add_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик +инфо ник текст (без упоминания)."""
    try:
        text = update.message.text.strip()
        
        if not text.startswith('+инфо '):
            return
        
        parts = text.split(' ', 2)
        if len(parts) < 3:
            await update.message.reply_text("❌ Формат: `+инфо username текст`", parse_mode='Markdown')
            return
        
        username = parts[1].strip().lstrip('@')  # Убираем @ если есть
        info_text = parts[2].strip()
        
        if not username or not info_text:
            await update.message.reply_text("❌ Укажите username и текст", parse_mode='Markdown')
            return
        
        success = add_user_info(username, info_text, update.effective_user.id)
        
        if success:
            await update.message.reply_text(
                f"✅ Информация о {username} успешно добавлена!",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text("❌ Не удалось добавить информацию")
            
    except Exception as e:
        logger.error(f"Ошибка добавления: {e}")
        await update.message.reply_text("❌ Ошибка при добавлении информации")

async def handle_delete_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик -инфо ник (без упоминания)."""
    try:
        text = update.message.text.strip()
        
        if not text.startswith('-инфо '):
            return
        
        parts = text.split(' ', 1)
        if len(parts) < 2:
            await update.message.reply_text("❌ Формат: `-инфо username`", parse_mode='Markdown')
            return
        
        username = parts[1].strip().lstrip('@')  # Убираем @ если есть
        if not username:
            await update.message.reply_text("❌ Укажите username", parse_mode='Markdown')
            return
        
        success = delete_user_info(username)
        
        if success:
            await update.message.reply_text(
                f"✅ Информация о {username} успешно удалена!",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                f"ℹ️ Информация о {username} не найдена.",
                parse_mode='Markdown'
            )
            
    except Exception as e:
        logger.error(f"Ошибка удаления: {e}")
        await update.message.reply_text("❌ Ошибка при удалении информации")

# ========== ОСТАВШИЕСЯ ФУНКЦИИ БЕЗ ИЗМЕНЕНИЙ ==========
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на кнопки."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == 'add_info':
        await query.edit_message_text(
            "📝 *Добавление информации*\n\n"
            "Отправьте сообщение в формате:\n"
            "`+инфо username текст информации`\n\n"
            "Пример:\n"
            "`+инфо ivanov любит котиков`",
            parse_mode='Markdown',
            reply_markup=get_back_keyboard()
        )
    
    elif data == 'delete_info':
        await query.edit_message_text(
            "🗑️ *Удаление информации*\n\n"
            "Отправьте сообщение в формате:\n"
            "`-инфо username`\n\n"
            "Пример:\n"
            "`-инфо ivanov`",
            parse_mode='Markdown',
            reply_markup=get_back_keyboard()
        )
    
    elif data == 'search_info':
        await query.edit_message_text(
            "🔍 *Поиск информации*\n\n"
            "Отправьте сообщение в формате:\n"
            "`!инфо username`\n\n"
            "Пример:\n"
            "`!инфо ivanov`",
            parse_mode='Markdown',
            reply_markup=get_back_keyboard()
        )
    
    elif data == 'all_info':
        await show_all_info_callback(query, context)
    
    elif data == 'db_management':
        user_id = query.from_user.id
        if is_owner(user_id):
            await query.edit_message_text(
                "⚙️ *Управление базой данных*\n\n"
                "Выберите действие:",
                parse_mode='Markdown',
                reply_markup=get_db_management_keyboard()
            )
        else:
            await query.edit_message_text(
                "⛔ *Доступ запрещен*\n\n"
                "Эта функция доступна только владельцу бота.",
                parse_mode='Markdown',
                reply_markup=get_back_keyboard()
            )
    
    elif data == 'create_backup':
        await create_backup_callback(query, context)
    
    elif data == 'import_db':
        await query.edit_message_text(
            "🔄 *Импорт базы данных*\n\n"
            "Отправьте файл `info.db` в этот чат.\n"
            "⚠️ *Внимание:* Текущая БД будет заменена!",
            parse_mode='Markdown',
            reply_markup=get_back_keyboard()
        )
    
    elif data == 'stats':
        await stats_callback(query, context)
    
    elif data == 'cleanup':
        await cleanup_callback(query, context)
    
    elif data == 'back_to_main':
        await query.edit_message_text(
            "🎮 *Главное меню*\n\n"
            "Выберите действие:",
            parse_mode='Markdown',
            reply_markup=get_main_menu_keyboard()
        )

async def create_backup_callback(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE):
    """Создает резервную копию БД."""
    user_id = query.from_user.id
    if not is_owner(user_id):
        await query.edit_message_text(
            "⛔ *Доступ запрещен*",
            parse_mode='Markdown',
            reply_markup=get_back_keyboard()
        )
        return
    
    backup_path = backup_database()
    if backup_path:
        with open(backup_path, 'rb') as f:
            await query.message.reply_document(
                document=f,
                filename=os.path.basename(backup_path),
                caption="💾 *Резервная копия создана!*",
                parse_mode='Markdown'
            )
        await query.edit_message_text(
            "✅ *Резервная копия успешно создана и отправлена!*",
            parse_mode='Markdown',
            reply_markup=get_back_keyboard()
        )
    else:
        await query.edit_message_text(
            "❌ *Не удалось создать резервную копию*",
            parse_mode='Markdown',
            reply_markup=get_back_keyboard()
        )

async def stats_callback(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE):
    """Показывает статистику БД."""
    user_id = query.from_user.id
    if not is_owner(user_id):
        await query.edit_message_text(
            "⛔ *Доступ запрещен*",
            parse_mode='Markdown',
            reply_markup=get_back_keyboard()
        )
        return
    
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM info")
        total = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(DISTINCT username) FROM info")
        unique_users = cursor.fetchone()[0]
        
        cursor.execute("SELECT MIN(added_date), MAX(added_date) FROM info")
        dates = cursor.fetchone()
        
        cursor.execute("SELECT added_by, COUNT(*) FROM info GROUP BY added_by ORDER BY COUNT(*) DESC LIMIT 5")
        top_adders = cursor.fetchall()
        
        conn.close()
        
        message = "📊 *Статистика базы данных*\n\n"
        message += f"• Всего записей: `{total}`\n"
        message += f"• Уникальных пользователей: `{unique_users}`\n"
        
        if dates[0] and dates[1]:
            min_date = datetime.strptime(dates[0], '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y')
            max_date = datetime.strptime(dates[1], '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y')
            message += f"• Период: `{min_date}` - `{max_date}`\n"
        
        if top_adders:
            message += "\n🏆 *Топ-5 по добавлению:*\n"
            for user_id, count in top_adders:
                message += f"  👤 {user_id}: `{count}` записей\n"
        
        await query.edit_message_text(message, parse_mode='Markdown', reply_markup=get_back_keyboard())
        
    except Exception as e:
        logger.error(f"Ошибка статистики: {e}")
        await query.edit_message_text(
            "❌ *Ошибка при получении статистики*",
            parse_mode='Markdown',
            reply_markup=get_back_keyboard()
        )

async def cleanup_callback(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE):
    """Очищает старые записи."""
    user_id = query.from_user.id
    if not is_owner(user_id):
        await query.edit_message_text(
            "⛔ *Доступ запрещен*",
            parse_mode='Markdown',
            reply_markup=get_back_keyboard()
        )
        return
    
    deleted_count = cleanup_database()
    await query.edit_message_text(
        f"🧹 *Очистка завершена!*\n\n"
        f"Удалено записей старше 30 дней: `{deleted_count}`",
        parse_mode='Markdown',
        reply_markup=get_back_keyboard()
    )

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик документов (импорт БД)."""
    try:
        user_id = update.effective_user.id
        
        # Проверяем владельца
        if not is_owner(user_id):
            # Игнорируем документы от не-владельцев
            return
        
        document = update.message.document
        
        # Проверяем, что это файл БД
        if not document.file_name or not document.file_name.endswith('.db'):
            await update.message.reply_text(
                "❌ *Неверный формат файла*\n\n"
                "Отправьте файл базы данных с расширением `.db`",
                parse_mode='Markdown'
            )
            return
        
        # Скачиваем файл
        temp_file = await document.get_file()
        temp_path = f"temp_{document.file_name}"
        await temp_file.download_to_drive(temp_path)
        
        # Проверяем структуру файла
        try:
            test_conn = sqlite3.connect(temp_path)
            test_cursor = test_conn.cursor()
            test_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='info'")
            if not test_cursor.fetchone():
                raise Exception("Таблица 'info' не найдена в файле")
            test_conn.close()
        except Exception as e:
            os.remove(temp_path)
            await update.message.reply_text(
                f"❌ *Неверная структура БД*\n\n"
                f"Ошибка: {str(e)}",
                parse_mode='Markdown'
            )
            return
        
        # Создаем бэкап текущей БД
        backup_path = backup_database()
        
        # Заменяем текущую БД
        shutil.copy2(temp_path, DB_FILE)
        os.remove(temp_path)
        
        # Получаем статистику импортированной БД
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM info")
        count = cursor.fetchone()[0]
        conn.close()
        
        await update.message.reply_text(
            f"✅ *База данных успешно импортирована!*\n\n"
            f"• Записей в БД: `{count}`\n"
            f"• Создан бэкап: `{os.path.basename(backup_path) if backup_path else 'нет'}`",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Ошибка импорта: {e}")
        await update.message.reply_text(
            f"❌ *Ошибка импорта БД*\n\n"
            f"Ошибка: {str(e)[:200]}",
            parse_mode='Markdown'
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик текстовых сообщений."""
    try:
        if not update.message or not update.message.text:
            return
        
        text = update.message.text
        
        # Обрабатываем команды
        if text.startswith('!инфо '):
            await handle_info_command(update, context)
        elif text.startswith('+инфо '):
            await handle_add_info(update, context)
        elif text.startswith('-инфо '):
            await handle_delete_info(update, context)
        elif text.lower() in ['меню', 'menu', 'start', 'начать']:
            await update.message.reply_text(
                "🎮 *Главное меню*\n\n"
                "Выберите действие:",
                parse_mode='Markdown',
                reply_markup=get_main_menu_keyboard()
            )
            
    except Exception as e:
        logger.error(f"Ошибка обработки сообщения: {e}")

# ========== ОСНОВНАЯ ФУНКЦИЯ ==========
def main():
    """Основная функция запуска бота."""
    # Инициализация БД
    init_db()
    
    # Очистка старых записей
    cleaned = cleanup_database()
    
    # Создаем приложение
    application = Application.builder().token(TOKEN).build()
    
    # Добавляем обработчики команд
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("tops", tops_command))
    
    # Обработчики сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    # Обработчики кнопок
    application.add_handler(CallbackQueryHandler(button_handler, pattern='^(add_info|delete_info|search_info|all_info|db_management|create_backup|import_db|stats|cleanup|back_to_main)$'))
    application.add_handler(CallbackQueryHandler(page_handler, pattern='^page_'))
    
    # Запуск бота
    print("=" * 50)
    print("ИНФОРМАЦИОННЫЙ БОТ ЗАПУЩЕН")
    print("=" * 50)
    print(f" Владелец: {ADMIN_IDS[0]}")
    print(f"🧹 Очищено записей: {cleaned}")
    print("=" * 50)
    print("📋 Основные команды:")
    print("• /start - Запустить бот")
    print("• /help - Справка")
    print("• /tops - Весь список")
    print("• +инфо ник текст - Добавить")
    print("• -инфо ник - Удалить")
    print("• !инфо ник - Найти")
    print("=" * 50)
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()

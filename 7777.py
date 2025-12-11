import logging
import sqlite3
import os
import shutil
import html
from datetime import datetime
from typing import Dict, List
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from telegram.ext import (
    Application, 
    CommandHandler, 
    MessageHandler, 
    CallbackQueryHandler, 
    ContextTypes, 
    filters
)
from telegram.error import BadRequest

# ========== КОНФИГУРАЦИЯ ==========
TOKEN = "8534057742:AAHWEBn4Z2FjKS5E9yEuaiEVoUBmKs5p1sM"
OWNER_ID = 6893832048  # ID владельца
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
    
    # Таблица для информации
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
    
    # Таблица для админов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            added_by INTEGER,
            added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_username ON info(username)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_id ON info(user_id)')
    
    # Добавляем владельца в таблицу админов
    cursor.execute(
        'INSERT OR IGNORE INTO admins (user_id, username, added_by) VALUES (?, ?, ?)',
        (OWNER_ID, 'owner', OWNER_ID)
    )
    
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
def escape_markdown(text: str) -> str:
    """Экранирует специальные символы Markdown."""
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return ''.join(['\\' + char if char in escape_chars else char for char in text])

def is_owner(user_id: int) -> bool:
    """Проверяет, является ли пользователь владельцем."""
    return user_id == OWNER_ID

def is_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь админом."""
    if user_id == OWNER_ID:
        return True
    
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # Сначала проверяем существование таблицы admins
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='admins'")
        if cursor.fetchone() is None:
            conn.close()
            return False
            
        cursor.execute('SELECT 1 FROM admins WHERE user_id = ?', (user_id,))
        result = cursor.fetchone() is not None
        conn.close()
        return result
    except Exception as e:
        logger.error(f"Ошибка при проверке админа: {e}")
        return False

def get_all_admins():
    """Получает список всех админов."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # Проверяем существование таблицы admins
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='admins'")
        if cursor.fetchone() is None:
            conn.close()
            return []
            
        cursor.execute('SELECT user_id, username FROM admins ORDER BY added_date')
        admins = cursor.fetchall()
        conn.close()
        return admins
    except Exception as e:
        logger.error(f"Ошибка при получении админов: {e}")
        return []

def add_admin_by_id(user_id: int, added_by: int) -> bool:
    """Добавляет админа по user_id."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # Создаем таблицу, если ее нет
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                added_by INTEGER,
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute(
            'INSERT OR REPLACE INTO admins (user_id, added_by) VALUES (?, ?)',
            (user_id, added_by)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Ошибка при добавлении админа: {e}")
        return False

def remove_admin(user_id: int) -> bool:
    """Удаляет админа (кроме владельца)."""
    if user_id == OWNER_ID:
        return False  # Нельзя удалить владельца
    
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM admins WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Ошибка при удалении админа: {e}")
        return False

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
    """Получает информацию о пользователе с ID записей."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, info_text, added_date FROM info WHERE username = ? ORDER BY added_date DESC",
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
    """Удаляет всю информацию о пользователе."""
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

def delete_specific_info(username: str, record_num: int):
    """Удаляет конкретную запись о пользователе по номеру."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        # Получаем все записи пользователя
        cursor.execute(
            "SELECT id FROM info WHERE username = ? ORDER BY added_date DESC",
            (username,)
        )
        records = cursor.fetchall()
        
        # Проверяем номер записи
        if record_num < 1 or record_num > len(records):
            return False
        
        # Удаляем конкретную запись
        record_id = records[record_num - 1][0]
        cursor.execute("DELETE FROM info WHERE id = ?", (record_id,))
        conn.commit()
        conn.close()
        
        return True
    except Exception as e:
        logger.error(f"Ошибка при удалении конкретной записи: {e}")
        return False

# ========== ФУНКЦИИ ПАГИНАЦИИ ==========
def create_pagination_keyboard(users: List[str], current_page: int, chat_type: str) -> InlineKeyboardMarkup:
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
    
    # Кнопка "Назад в меню" - для лички показываем меню, для группы просто удаляем сообщение
    if chat_type == 'private':
        keyboard.append([InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')])
    
    return InlineKeyboardMarkup(keyboard)

def get_paginated_users(users: List[str], page: int = 0, items_per_page: int = 10) -> tuple:
    """Возвращает пользователей для конкретной страницы."""
    start_idx = page * items_per_page
    end_idx = min(start_idx + items_per_page, len(users))
    return users[start_idx:end_idx], len(users)

# ========== КЛАВИАТУРЫ ==========
def get_main_menu_keyboard(chat_type: str, user_id: int):
    """Клавиатура главного меню с учетом типа чата."""
    keyboard = [
        [InlineKeyboardButton("📋 Весь список", callback_data='all_info')],
    ]
    
    # Добавляем админ-панель только в личных сообщениях и только для админов
    if chat_type == 'private' and is_admin(user_id):
        keyboard.append([InlineKeyboardButton("⚙️ Управление", callback_data='management')])
    
    return InlineKeyboardMarkup(keyboard)

def get_management_keyboard(user_id: int):
    """Клавиатура управления (для админов в личке)."""
    keyboard = []
    
    # Владелец видит все опции
    if is_owner(user_id):
        keyboard.extend([
            [InlineKeyboardButton("👥 Управление админами", callback_data='manage_admins')],
            [InlineKeyboardButton("💾 Создать бэкап", callback_data='create_backup')],
            [InlineKeyboardButton("🔄 Импорт БД", callback_data='import_db')],
            [InlineKeyboardButton("📊 Статистика", callback_data='stats')],
            [InlineKeyboardButton("🧹 Очистка", callback_data='cleanup')],
        ])
    else:
        # Обычные админы видят только ограниченный набор
        keyboard.extend([
            [InlineKeyboardButton("📊 Статистика", callback_data='stats')],
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='back_to_main')])
    return InlineKeyboardMarkup(keyboard)

def get_admins_management_keyboard():
    """Клавиатура управления админами (только для владельца)."""
    keyboard = [
        [InlineKeyboardButton("➕ Добавить админа по ID", callback_data='add_admin_by_id')],
        [InlineKeyboardButton("➖ Удалить админа по ID", callback_data='remove_admin_by_id')],
        [InlineKeyboardButton("📋 Список админов", callback_data='list_admins')],
        [InlineKeyboardButton("🔙 Назад", callback_data='back_to_management')]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_back_keyboard(chat_type: str):
    """Кнопка возврата с учетом типа чата."""
    if chat_type == 'private':
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data='back_to_main')]]
        return InlineKeyboardMarkup(keyboard)
    return None

# ========== БЕЗОПАСНОЕ РЕДАКТИРОВАНИЕ СООБЩЕНИЙ ==========
async def safe_edit_message_text(query: CallbackQuery, text: str, parse_mode: str = None, reply_markup: InlineKeyboardMarkup = None):
    """Безопасное редактирование сообщения с обработкой ошибок."""
    try:
        await query.edit_message_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            raise

# ========== ОБРАБОТЧИКИ КОМАНД ==========
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start."""
    chat_type = update.effective_chat.type
    user_id = update.effective_user.id
    
    welcome_text = (
        "🎮 *Информационный Бот*\n\n"
        "✨ *Возможности:*\n"
        "• 📋 Просмотр всей информации (/tops)\n"
        "• 🔍 Поиск информации о пользователях\n"
    )
    
    # Для админов в личке показываем дополнительные возможности
    if chat_type == 'private' and is_admin(user_id):
        welcome_text += "• ⚙️ Управление (для админов)\n"
    
    await update.message.reply_text(
        welcome_text,
        parse_mode='Markdown',
        reply_markup=get_main_menu_keyboard(chat_type, user_id)
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /help."""
    user_id = update.effective_user.id
    
    help_text = (
        "🎮 *Информационный Бот - Справка*\n\n"
        "✨ *Основные команды:*\n"
        "`/start` - Запустить бота\n"
        "`/help` - Эта справка\n"
        "`/tops` - Весь список информации\n\n"
    )
    
    # Для админов показываем команды управления
    if is_admin(user_id):
        help_text += (
            "📝 *Команды для админов (в группе и личке):*\n"
            "`+инфо username текст` - Добавить информацию\n"
            "`-инфо username` - Удалить всю информацию\n"
            "`--инфо username номер` - Удалить конкретную запись\n"
            "`!инфо username` - Найти информацию\n\n"
        )
        
        if is_owner(user_id):
            help_text += (
                "⚙️ *Команды для владельца:*\n"
                "`/addadmin <ID>` - Добавить админа по ID\n"
                "`/removeadmin <ID>` - Удалить админа по ID\n"
                "`/listadmins` - Список админов\n"
                "`/stats` - Статистика\n"
                "`/backup` - Создать бэкап\n"
                "`/cleanup` - Очистка\n\n"
            )
    else:
        help_text += (
            "🔍 *Поиск информации (все):*\n"
            "`!инфо username` - Найти информацию\n\n"
            "*Примечание:* Команды добавления/удаления доступны только админам.\n"
        )
    
    help_text += "💾 *Импорт БД (владелец):*\nОтправьте файл `info.db` в личку бота"
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def tops_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /tops."""
    await show_all_info(update, context)

async def addadmin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавление админа по ID (только для владельца)."""
    user_id = update.effective_user.id
    
    if not is_owner(user_id):
        await update.message.reply_text("❌ *Эта команда доступна только владельцу*", parse_mode='Markdown')
        return
    
    if not context.args:
        await update.message.reply_text("❌ *Укажите ID пользователя:* `/addadmin <ID>`", parse_mode='Markdown')
        return
    
    try:
        target_user_id = int(context.args[0].strip())
    except ValueError:
        await update.message.reply_text("❌ *Неверный ID. ID должен быть числом.*", parse_mode='Markdown')
        return
    
    if add_admin_by_id(target_user_id, user_id):
        await update.message.reply_text(f"✅ *Пользователь с ID {target_user_id} добавлен в админы!*", parse_mode='Markdown')
    else:
        await update.message.reply_text("❌ *Не удалось добавить админа*", parse_mode='Markdown')

async def removeadmin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удаление админа по ID (только для владельца)."""
    user_id = update.effective_user.id
    
    if not is_owner(user_id):
        await update.message.reply_text("❌ *Эта команда доступна только владельцу*", parse_mode='Markdown')
        return
    
    if not context.args:
        await update.message.reply_text("❌ *Укажите ID пользователя:* `/removeadmin <ID>`", parse_mode='Markdown')
        return
    
    try:
        target_user_id = int(context.args[0].strip())
    except ValueError:
        await update.message.reply_text("❌ *Неверный ID. ID должен быть числом.*", parse_mode='Markdown')
        return
    
    if target_user_id == OWNER_ID:
        await update.message.reply_text("❌ *Нельзя удалить владельца*", parse_mode='Markdown')
        return
    
    if remove_admin(target_user_id):
        await update.message.reply_text(f"✅ *Админ с ID {target_user_id} успешно удален*", parse_mode='Markdown')
    else:
        await update.message.reply_text("❌ *Не удалось удалить админа или админ не найден*", parse_mode='Markdown')

async def listadmins_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Список админов (только для владельца)."""
    user_id = update.effective_user.id
    
    if not is_owner(user_id):
        await update.message.reply_text("❌ *Эта команда доступна только владельцу*", parse_mode='Markdown')
        return
    
    admins = get_all_admins()
    
    if not admins:
        await update.message.reply_text("📭 *Список админов пуст*", parse_mode='Markdown')
        return
    
    message = "👥 *Список админов:*\n\n"
    
    for i, (admin_id, username) in enumerate(admins, 1):
        username_display = f"@{username}" if username else f"ID: {admin_id}"
        role = "👑 Владелец" if admin_id == OWNER_ID else "👤 Админ"
        message += f"{i}. {username_display} - {role}\n"
    
    await update.message.reply_text(message, parse_mode='Markdown')

# ========== ОБНОВЛЕННЫЕ ФУНКЦИИ ПАГИНАЦИИ ==========
async def show_all_info_callback(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE):
    """Показывает всю информацию с пагинацией (через callback)."""
    users = get_all_users()
    
    if not users:
        chat_type = query.message.chat.type
        user_id = query.from_user.id
        await safe_edit_message_text(
            query,
            "📭 *База данных пуста*\n\n"
            "Добавьте информацию с помощью команды: +инфо username текст",
            parse_mode='Markdown',
            reply_markup=get_main_menu_keyboard(chat_type, user_id)
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
        chat_type = query.message.chat.type
        await safe_edit_message_text(
            query,
            "📭 *На этой странице нет данных*",
            parse_mode='Markdown',
            reply_markup=get_back_keyboard(chat_type)
        )
        return
    
    message = f"📋 *Весь список информации*\n"
    message += f"Страница {current_page + 1} из {total_pages}\n"
    message += f"Всего пользователей: {total_users}\n\n"
    
    # Вычисляем начальный номер для текущей страницы
    start_number = current_page * items_per_page + 1
    
    for i, username in enumerate(page_users, start_number):
        info_list = get_user_info(username)
        if info_list:
            # Экранируем username для Markdown
            safe_username = escape_markdown(username)
            display_username = f"@{safe_username}" if not username.startswith('@') else safe_username
            message += f"{i}. 👤 *{display_username}*\n"
            
            for j, (_, text, date) in enumerate(info_list[:3], 1):
                date_str = datetime.strptime(date, '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y')
                # Экранируем текст для Markdown
                safe_text = escape_markdown(text)
                message += f"   {j}. {safe_text} ({date_str})\n"
            message += "\n"
    
    # Создаем клавиатуру пагинации с полной навигацией
    chat_type = query.message.chat.type
    reply_markup = create_pagination_keyboard(users, current_page, chat_type)
    
    await safe_edit_message_text(query, message, parse_mode='Markdown', reply_markup=reply_markup)

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
    
    # Вычисляем начальный номер для текущей страницы
    start_number = current_page * items_per_page + 1
    
    for i, username in enumerate(page_users, start_number):
        info_list = get_user_info(username)
        if info_list:
            # Экранируем username для Markdown
            safe_username = escape_markdown(username)
            display_username = f"@{safe_username}" if not username.startswith('@') else safe_username
            message += f"{i}. 👤 *{display_username}*\n"
            
            for j, (_, text, date) in enumerate(info_list[:3], 1):
                date_str = datetime.strptime(date, '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y')
                # Экранируем текст для Markdown
                safe_text = escape_markdown(text)
                message += f"   {j}. {safe_text} ({date_str})\n"
            message += "\n"
    
    # Создаем клавиатуру пагинации
    chat_type = update.effective_chat.type
    reply_markup = create_pagination_keyboard(users, current_page, chat_type)
    
    await update.message.reply_text(message, parse_mode='Markdown', reply_markup=reply_markup)

# ========== ОБРАБОТЧИКИ СООБЩЕНИЙ ==========
async def handle_info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик !инфо ник (доступен всем в группе)."""
    try:
        text = update.message.text.strip()
        
        if not text.startswith('!инфо '):
            return
        
        parts = text.split(' ', 1)
        if len(parts) < 2:
            await update.message.reply_text("❌ Формат: `!инфо username`", parse_mode='Markdown')
            return
        
        username = parts[1].strip().lstrip('@')
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
        
        # Экранируем username для Markdown
        safe_username = escape_markdown(username)
        display_username = f"@{safe_username}" if not username.startswith('@') else safe_username
        response = f"📋 *Информация о {display_username}:*\n\n"
        
        for i, (_, text, date) in enumerate(info_list, 1):
            date_str = datetime.strptime(date, '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y %H:%M')
            # Экранируем текст для Markdown
            safe_text = escape_markdown(text)
            response += f"{i}. {safe_text}\n   📅 {date_str}\n\n"
        
        await update.message.reply_text(response, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Ошибка поиска: {e}")
        await update.message.reply_text("❌ Ошибка при поиске информации")

async def handle_add_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик +инфо ник текст (для админов в группе и личке)."""
    try:
        user_id = update.effective_user.id
        
        # Проверяем, что пользователь админ
        if not is_admin(user_id):
            return
        
        text = update.message.text.strip()
        
        if not text.startswith('+инфо '):
            return
        
        parts = text.split(' ', 2)
        if len(parts) < 3:
            await update.message.reply_text("❌ Формат: `+инфо username текст`", parse_mode='Markdown')
            return
        
        username = parts[1].strip().lstrip('@')
        info_text = parts[2].strip()
        
        if not username or not info_text:
            await update.message.reply_text("❌ Укажите username и текст", parse_mode='Markdown')
            return
        
        success = add_user_info(username, info_text, user_id)
        
        if success:
            # Экранируем username для Markdown
            safe_username = escape_markdown(username)
            display_username = f"@{safe_username}" if not username.startswith('@') else safe_username
            await update.message.reply_text(
                f"✅ Информация о {display_username} успешно добавлена!",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text("❌ Не удалось добавить информацию")
            
    except Exception as e:
        logger.error(f"Ошибка добавления: {e}")
        await update.message.reply_text("❌ Ошибка при добавлении информации")

async def handle_delete_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик -инфо username (удалить все) и --инфо username номер (удалить конкретную)."""
    try:
        user_id = update.effective_user.id
        
        # Проверяем, что пользователь админ
        if not is_admin(user_id):
            return
        
        text = update.message.text.strip()
        
        # Проверяем команду удаления всей информации
        if text.startswith('-инфо ') and not text.startswith('--инфо'):
            parts = text.split(' ', 1)
            if len(parts) < 2:
                await update.message.reply_text("❌ Формат: `-инфо username`", parse_mode='Markdown')
                return
            
            username = parts[1].strip().lstrip('@')
            if not username:
                await update.message.reply_text("❌ Укажите username", parse_mode='Markdown')
                return
            
            success = delete_user_info(username)
            
            if success:
                safe_username = escape_markdown(username)
                display_username = f"@{safe_username}" if not username.startswith('@') else safe_username
                await update.message.reply_text(
                    f"✅ Вся информация о {display_username} успешно удалена!",
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(
                    f"ℹ️ Информация о {username} не найдена.",
                    parse_mode='Markdown'
                )
        
        # Проверяем команду удаления конкретной записи
        elif text.startswith('--инфо '):
            parts = text.split(' ', 2)
            if len(parts) < 3:
                await update.message.reply_text("❌ Формат: `--инфо username номер`", parse_mode='Markdown')
                return
            
            username = parts[1].strip().lstrip('@')
            record_num_str = parts[2].strip()
            
            if not username or not record_num_str:
                await update.message.reply_text("❌ Укажите username и номер записи", parse_mode='Markdown')
                return
            
            try:
                record_num = int(record_num_str)
                if record_num < 1:
                    await update.message.reply_text("❌ Номер записи должен быть положительным числом", parse_mode='Markdown')
                    return
            except ValueError:
                await update.message.reply_text("❌ Укажите корректный номер записи", parse_mode='Markdown')
                return
            
            success = delete_specific_info(username, record_num)
            
            if success:
                safe_username = escape_markdown(username)
                display_username = f"@{safe_username}" if not username.startswith('@') else safe_username
                await update.message.reply_text(
                    f"✅ Запись №{record_num} о {display_username} успешно удалена!",
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text(
                    f"❌ Не удалось удалить запись №{record_num} о {username}.\n"
                    f"Возможно, такой записи не существует.",
                    parse_mode='Markdown'
                )
            
    except Exception as e:
        logger.error(f"Ошибка удаления: {e}")
        await update.message.reply_text("❌ Ошибка при удалении информации")

# ========== ОБРАБОТЧИКИ КНОПОК ==========
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на кнопки."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    chat_type = query.message.chat.type
    
    if data == 'all_info':
        await safe_edit_message_text(
            query,
            "⏳ *Загружаю список...*",
            parse_mode='Markdown'
        )
        await show_all_info_callback(query, context)
    
    elif data == 'management':
        # Проверяем, что это личное сообщение и пользователь админ
        if chat_type != 'private':
            await safe_edit_message_text(
                query,
                "⛔ *Эта функция доступна только в личном чате с ботом*",
                parse_mode='Markdown'
            )
            return
            
        if not is_admin(user_id):
            await safe_edit_message_text(
                query,
                "⛔ *Доступ запрещен*\n\n"
                "Эта функция доступна только админам.",
                parse_mode='Markdown'
            )
            return
        
        await safe_edit_message_text(
            query,
            "⚙️ *Управление*\n\n"
            "Выберите действие:",
            parse_mode='Markdown',
            reply_markup=get_management_keyboard(user_id)
        )
    
    elif data == 'manage_admins':
        if not is_owner(user_id) or chat_type != 'private':
            await safe_edit_message_text(
                query,
                "⛔ *Эта функция доступна только владельцу в личном чате*",
                parse_mode='Markdown'
            )
            return
        
        await safe_edit_message_text(
            query,
            "👥 *Управление админами*\n\n"
            "Выберите действие:",
            parse_mode='Markdown',
            reply_markup=get_admins_management_keyboard()
        )
    
    elif data == 'add_admin_by_id':
        if not is_owner(user_id) or chat_type != 'private':
            await safe_edit_message_text(
                query,
                "⛔ *Эта функция доступна только владельцу в личном чате*",
                parse_mode='Markdown'
            )
            return
        
        await safe_edit_message_text(
            query,
            "➕ *Добавление админа по ID*\n\n"
            "Для добавления админа отправьте команду:\n"
            "`/addadmin <ID>`\n\n"
            "Пример:\n"
            "`/addadmin 123456789`",
            parse_mode='Markdown',
            reply_markup=get_back_keyboard(chat_type)
        )
    
    elif data == 'remove_admin_by_id':
        if not is_owner(user_id) or chat_type != 'private':
            await safe_edit_message_text(
                query,
                "⛔ *Эта функция доступна только владельцу в личном чате*",
                parse_mode='Markdown'
            )
            return
        
        await safe_edit_message_text(
            query,
            "➖ *Удаление админа по ID*\n\n"
            "Для удаления админа отправьте команду:\n"
            "`/removeadmin <ID>`\n\n"
            "Пример:\n"
            "`/removeadmin 123456789`",
            parse_mode='Markdown',
            reply_markup=get_back_keyboard(chat_type)
        )
    
    elif data == 'list_admins':
        if not is_owner(user_id) or chat_type != 'private':
            await safe_edit_message_text(
                query,
                "⛔ *Эта функция доступна только владельцу в личном чате*",
                parse_mode='Markdown'
            )
            return
        
        admins = get_all_admins()
        
        if not admins:
            await safe_edit_message_text(
                query,
                "📭 *Список админов пуст*",
                parse_mode='Markdown',
                reply_markup=get_back_keyboard(chat_type)
            )
            return
        
        message = "👥 *Список админов:*\n\n"
        
        for i, (admin_id, username) in enumerate(admins, 1):
            username_display = f"@{username}" if username else f"ID: {admin_id}"
            role = "👑 Владелец" if admin_id == OWNER_ID else "👤 Админ"
            message += f"{i}. {username_display} - {role}\n"
        
        await safe_edit_message_text(
            query,
            message,
            parse_mode='Markdown',
            reply_markup=get_back_keyboard(chat_type)
        )
    
    elif data == 'back_to_management':
        if chat_type != 'private' or not is_admin(user_id):
            await safe_edit_message_text(
                query,
                "⛔ *Доступ запрещен*",
                parse_mode='Markdown'
            )
            return
        
        await safe_edit_message_text(
            query,
            "⚙️ *Управление*\n\n"
            "Выберите действие:",
            parse_mode='Markdown',
            reply_markup=get_management_keyboard(user_id)
        )
    
    elif data == 'create_backup':
        if not is_owner(user_id) or chat_type != 'private':
            await safe_edit_message_text(
                query,
                "⛔ *Эта функция доступна только владельцу в личном чате*",
                parse_mode='Markdown'
            )
            return
        
        await create_backup_callback(query, context)
    
    elif data == 'import_db':
        if not is_owner(user_id) or chat_type != 'private':
            await safe_edit_message_text(
                query,
                "⛔ *Эта функция доступна только владельцу в личном чате*",
                parse_mode='Markdown'
            )
            return
        
        await safe_edit_message_text(
            query,
            "🔄 *Импорт базы данных*\n\n"
            "Отправьте файл `info.db` в этот чат.\n"
            "⚠️ *Внимание:* Текущая БД будет заменена!",
            parse_mode='Markdown',
            reply_markup=get_back_keyboard(chat_type)
        )
    
    elif data == 'stats':
        if chat_type != 'private' or not is_admin(user_id):
            await safe_edit_message_text(
                query,
                "⛔ *Эта функция доступна только админам в личном чате*",
                parse_mode='Markdown'
            )
            return
        
        await stats_callback(query, context)
    
    elif data == 'cleanup':
        if not is_owner(user_id) or chat_type != 'private':
            await safe_edit_message_text(
                query,
                "⛔ *Эта функция доступна только владельцу в личном чате*",
                parse_mode='Markdown'
            )
            return
        
        await cleanup_callback(query, context)
    
    elif data == 'back_to_main':
        await safe_edit_message_text(
            query,
            "🎮 *Главное меню*\n\n"
            "Выберите действие:",
            parse_mode='Markdown',
            reply_markup=get_main_menu_keyboard(chat_type, user_id)
        )

async def create_backup_callback(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE):
    """Создает резервную копию БД."""
    user_id = query.from_user.id
    chat_type = query.message.chat.type
    
    if not is_owner(user_id) or chat_type != 'private':
        await safe_edit_message_text(
            query,
            "⛔ *Эта функция доступна только владельцу в личном чате*",
            parse_mode='Markdown'
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
        await safe_edit_message_text(
            query,
            "✅ *Резервная копия успешно создана и отправлена!*",
            parse_mode='Markdown',
            reply_markup=get_back_keyboard(chat_type)
        )
    else:
        await safe_edit_message_text(
            query,
            "❌ *Не удалось создать резервную копию*",
            parse_mode='Markdown',
            reply_markup=get_back_keyboard(chat_type)
        )

async def stats_callback(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE):
    """Показывает статистику БД."""
    user_id = query.from_user.id
    chat_type = query.message.chat.type
    
    if not is_admin(user_id) or chat_type != 'private':
        await safe_edit_message_text(
            query,
            "⛔ *Эта функция доступна только админам в личном чате*",
            parse_mode='Markdown'
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
            for adder_id, count in top_adders:
                message += f"  👤 `{adder_id}`: `{count}` записей\n"
        
        await safe_edit_message_text(message, parse_mode='Markdown', reply_markup=get_back_keyboard(chat_type))
        
    except Exception as e:
        logger.error(f"Ошибка статистики: {e}")
        await safe_edit_message_text(
            query,
            "❌ *Ошибка при получении статистики*",
            parse_mode='Markdown',
            reply_markup=get_back_keyboard(chat_type)
        )

async def cleanup_callback(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE):
    """Очищает старые записи."""
    user_id = query.from_user.id
    chat_type = query.message.chat.type
    
    if not is_owner(user_id) or chat_type != 'private':
        await safe_edit_message_text(
            query,
            "⛔ *Эта функция доступна только владельцу в личном чате*",
            parse_mode='Markdown'
        )
        return
    
    deleted_count = cleanup_database()
    await safe_edit_message_text(
        query,
        f"🧹 *Очистка завершена!*\n\n"
        f"Удалено записей старше 30 дней: `{deleted_count}`",
        parse_mode='Markdown',
        reply_markup=get_back_keyboard(chat_type)
    )

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик документов (импорт БД)."""
    try:
        user_id = update.effective_user.id
        chat_type = update.effective_chat.type
        
        # Проверяем владельца и тип чата
        if not is_owner(user_id) or chat_type != 'private':
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
        chat_type = update.effective_chat.type
        
        # Обрабатываем команды
        if text.startswith('!инфо '):
            await handle_info_command(update, context)
        elif text.startswith('+инфо '):
            await handle_add_info(update, context)
        elif text.startswith('-инфо ') or text.startswith('--инфо '):
            await handle_delete_info(update, context)
        elif text.lower() in ['меню', 'menu', 'start', 'начать']:
            user_id = update.effective_user.id
            await update.message.reply_text(
                "🎮 *Главное меню*\n\n"
                "Выберите действие:",
                parse_mode='Markdown',
                reply_markup=get_main_menu_keyboard(chat_type, user_id)
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
    application.add_handler(CommandHandler("addadmin", addadmin_command))
    application.add_handler(CommandHandler("removeadmin", removeadmin_command))
    application.add_handler(CommandHandler("listadmins", listadmins_command))
    
    # Обработчики сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    # Обработчики кнопок
    application.add_handler(CallbackQueryHandler(button_handler, pattern='^(all_info|management|manage_admins|add_admin_by_id|remove_admin_by_id|list_admins|back_to_management|create_backup|import_db|stats|cleanup|back_to_main)$'))
    application.add_handler(CallbackQueryHandler(page_handler, pattern='^page_'))
    
    # Запуск бота
    print("=" * 50)
    print("ИНФОРМАЦИОННЫЙ БОТ ЗАПУЩЕН")
    print("=" * 50)
    print(f" Владелец: {OWNER_ID}")
    print(f"🧹 Очищено записей: {cleaned}")
    print("=" * 50)
    print("📋 Основные команды:")
    print("• /start - Запустить бот")
    print("• /help - Справка")
    print("• /tops - Весь список")
    print("• !инфо ник - Найти информацию (все)")
    print("• +инфо ник текст - Добавить (админы в группе/личке)")
    print("• -инфо ник - Удалить все (админы в группе/личке)")
    print("• --инфо ник номер - Удалить конкретную запись (админы в группе/личке)")
    print("=" * 50)
    print(" Команды владельца:")
    print("• /addadmin <ID> - Добавить админа по ID")
    print("• /removeadmin <ID> - Удалить админа по ID")
    print("• /listadmins - Список админов")
    print("=" * 50)
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()


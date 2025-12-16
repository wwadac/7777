import logging
import sqlite3
import os
import json
import shutil
import html
from datetime import datetime
from typing import Dict, List, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)
from telegram.error import TelegramError, BadRequest

# ==============================================================================
#                                   НАСТРОЙКИ
# ==============================================================================

# Токен бота (используйте нужный)
BOT_TOKEN = "8534057742:AAE1EDuHUmBXo0vxsXR5XorlWgeXe3-4L98"

# ID Владельца (для админки инфо-бота)
OWNER_ID = 6893832048

# ID Группы для архива (куда создаются темы)
ARCHIVE_GROUP_ID = -1003606590827

# Файлы данных
DB_FILE = "info.db"              # SQLite для инфо-бота
TOPICS_FILE = "user_topics.json" # JSON для связки тем архива
BACKUP_DIR = "backups"
LOG_FILE = "bot.log"

# ==============================================================================
#                                   ЛОГИРОВАНИЕ
# ==============================================================================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ==============================================================================
#                       РАБОТА С JSON (АРХИВАТОР)
# ==============================================================================
def load_topics() -> dict:
    """Загрузка маппинга пользователей к темам"""
    if os.path.exists(TOPICS_FILE):
        try:
            with open(TOPICS_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Ошибка чтения topics: {e}")
    return {}

def save_topics(topics: dict):
    """Сохранение маппинга"""
    with open(TOPICS_FILE, "w") as f:
        json.dump(topics, f, indent=2)

async def get_or_create_topic(context: ContextTypes.DEFAULT_TYPE, user_id: int, username: str, first_name: str) -> Optional[int]:
    """Получить ID темы в группе-архиве или создать новую"""
    topics = load_topics()
    user_key = str(user_id)
    
    # Если тема уже есть — возвращаем её ID
    if user_key in topics:
        return topics[user_key]
    
    # Создаём новую тему
    display_name = f"@{username}" if username else first_name or f"User_{user_id}"
    
    try:
        # Создание темы в группе
        forum_topic = await context.bot.create_forum_topic(
            chat_id=ARCHIVE_GROUP_ID,
            name=display_name,
            icon_custom_emoji_id=None
        )
        
        topic_id = forum_topic.message_thread_id
        
        # Сохраняем связку
        topics[user_key] = topic_id
        save_topics(topics)
        
        # Первое сообщение с инфой о пользователе
        info_text = f"""👤 **Новый пользователь в архиве**

🆔 ID: `{user_id}`
👤 Имя: {first_name or "—"}
📧 Username: @{username or "нет"}
📅 Дата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        await context.bot.send_message(
            chat_id=ARCHIVE_GROUP_ID,
            message_thread_id=topic_id,
            text=info_text,
            parse_mode="Markdown"
        )
        return topic_id
        
    except TelegramError as e:
        logger.error(f"❌ Ошибка создания темы для {user_id}: {e}")
        return None

# ==============================================================================
#                       РАБОТА С SQLite (ИНФО-БОТ)
# ==============================================================================
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

# --- Helpers for DB ---
def escape_markdown(text: str) -> str:
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return ''.join(['\\' + char if char in escape_chars else char for char in text])

def is_owner(user_id: int) -> bool:
    return user_id == OWNER_ID

def is_admin(user_id: int) -> bool:
    if user_id == OWNER_ID:
        return True
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
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
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='admins'")
        if cursor.fetchone() is None:
            conn.close()
            return []
        cursor.execute('SELECT user_id, username FROM admins ORDER BY added_date')
        admins = cursor.fetchall()
        conn.close()
        return admins
    except Exception:
        return []

def add_admin_by_id(user_id: int, added_by: int) -> bool:
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO admins (user_id, added_by) VALUES (?, ?)', (user_id, added_by))
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False

def remove_admin(user_id: int) -> bool:
    if user_id == OWNER_ID: return False
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('DELETE FROM admins WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False

def get_all_users():
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT username FROM info ORDER BY username")
        users = [row[0] for row in cursor.fetchall()]
        conn.close()
        return users
    except Exception:
        return []

def get_user_info(username: str):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT id, info_text, added_date FROM info WHERE username = ? ORDER BY added_date DESC", (username,))
        info = cursor.fetchall()
        conn.close()
        return info
    except Exception:
        return []

def add_user_info(username: str, info_text: str, added_by: int):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO info (user_id, username, info_text, added_by) VALUES (0, ?, ?, ?)", (username, info_text, added_by))
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False

def delete_user_info(username: str):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM info WHERE username = ?", (username,))
        del_count = cursor.rowcount
        conn.commit()
        conn.close()
        return del_count > 0
    except Exception:
        return False

def delete_specific_info(username: str, record_num: int):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM info WHERE username = ? ORDER BY added_date DESC", (username,))
        records = cursor.fetchall()
        if record_num < 1 or record_num > len(records):
            return False
        record_id = records[record_num - 1][0]
        cursor.execute("DELETE FROM info WHERE id = ?", (record_id,))
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False

# ==============================================================================
#                       КЛАВИАТУРЫ И ПАГИНАЦИЯ
# ==============================================================================
def create_pagination_keyboard(users: List[str], current_page: int, chat_type: str) -> InlineKeyboardMarkup:
    items_per_page = 10
    total_pages = (len(users) + items_per_page - 1) // items_per_page
    keyboard = []
    nav_buttons = []
    
    if current_page > 0:
        nav_buttons.append(InlineKeyboardButton("⏮️", callback_data=f'page_0'))
    if current_page > 0:
        nav_buttons.append(InlineKeyboardButton("◀️", callback_data=f'page_{current_page-1}'))
    
    info_button = InlineKeyboardButton(f"📄 {current_page+1}/{total_pages}", callback_data="noop")
    nav_buttons.append(info_button)
    
    if current_page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("▶️", callback_data=f'page_{current_page+1}'))
    if current_page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("⏭️", callback_data=f'page_{total_pages-1}'))
    
    if nav_buttons: keyboard.append(nav_buttons)
    if chat_type == 'private':
        keyboard.append([InlineKeyboardButton("🔙 Меню", callback_data='back_to_main')])
    
    return InlineKeyboardMarkup(keyboard)

def get_paginated_users(users: List[str], page: int = 0, items_per_page: int = 10) -> tuple:
    start_idx = page * items_per_page
    end_idx = min(start_idx + items_per_page, len(users))
    return users[start_idx:end_idx], len(users)

def get_main_menu_keyboard(chat_type: str, user_id: int):
    keyboard = [[InlineKeyboardButton("📋 Список Инфо", callback_data='all_info')]]
    if chat_type == 'private' and is_admin(user_id):
        keyboard.append([InlineKeyboardButton("⚙️ Админка", callback_data='management')])
    return InlineKeyboardMarkup(keyboard)

def get_management_keyboard(user_id: int):
    keyboard = []
    if is_owner(user_id):
        keyboard.extend([
            [InlineKeyboardButton("👥 Админы", callback_data='manage_admins')],
            [InlineKeyboardButton("💾 Бэкап", callback_data='create_backup')],
            [InlineKeyboardButton("🔄 Импорт БД", callback_data='import_db')],
            [InlineKeyboardButton("📊 Статистика", callback_data='stats')],
            [InlineKeyboardButton("🧹 Очистка", callback_data='cleanup')],
        ])
    else:
        keyboard.extend([[InlineKeyboardButton("📊 Статистика", callback_data='stats')]])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='back_to_main')])
    return InlineKeyboardMarkup(keyboard)

def get_admins_management_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Добавить по ID", callback_data='add_admin_by_id')],
        [InlineKeyboardButton("➖ Удалить по ID", callback_data='remove_admin_by_id')],
        [InlineKeyboardButton("📋 Список", callback_data='list_admins')],
        [InlineKeyboardButton("🔙 Назад", callback_data='back_to_management')]
    ])

def get_back_keyboard(chat_type: str):
    if chat_type == 'private':
        return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data='back_to_main')]])
    return None

async def safe_edit_message_text(query: CallbackQuery, text: str, parse_mode: str = None, reply_markup: InlineKeyboardMarkup = None):
    try:
        await query.edit_message_text(text, parse_mode=parse_mode, reply_markup=reply_markup)
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            raise

# ==============================================================================
#                       ОСНОВНЫЕ ОБРАБОТЧИКИ (КОМАНДЫ)
# ==============================================================================

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Объединенный старт"""
    chat_type = update.effective_chat.type
    user_id = update.effective_user.id
    
    welcome_text = (
        "👋 *Привет! Я мультифункциональный бот.*\n\n"
        "📁 *Архиватор:*\n"
        "Отправляй мне сообщения (текст, фото, видео, гс), и я сохраню их в твою личную тему в архиве.\n\n"
        "ℹ️ *Инфо-база:*\n"
        "Я храню информацию о пользователях.\n"
        "• `/tops` или кнопка ниже — список всех записей\n"
        "• `!инфо username` — поиск информации\n"
    )
    
    if chat_type == 'private' and is_admin(user_id):
        welcome_text += "\n⚙️ *Для админов доступны инструменты управления.*"

    await update.message.reply_text(
        welcome_text,
        parse_mode='Markdown',
        reply_markup=get_main_menu_keyboard(chat_type, user_id)
    )

async def cmd_my_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ссылка на тему архива"""
    topics = load_topics()
    user_key = str(update.effective_user.id)
    
    if user_key in topics:
        topic_id = topics[user_key]
        group_id_str = str(ARCHIVE_GROUP_ID).replace("-100", "")
        link = f"https://t.me/c/{group_id_str}/{topic_id}"
        await update.message.reply_text(f"📁 Твоя тема в архиве: {link}")
    else:
        await update.message.reply_text("📭 У тебя пока нет сохранённых сообщений.")

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = (
        "🤖 *Справка по командам*\n\n"
        "📁 `/mytopic` - ссылка на твой архив\n"
        "ℹ️ `/tops` - список всей информации\n"
        "🔍 `!инфо ник` - поиск информации\n\n"
    )
    if is_admin(user_id):
        text += (
            "🛠 *Админ-команды:*\n"
            "`+инфо ник текст` - добавить\n"
            "`-инфо ник` - удалить всё\n"
            "`--инфо ник номер` - удалить запись\n"
        )
        if is_owner(user_id):
            text += (
                "\n👑 *Владелец:*\n"
                "`/addadmin ID`, `/removeadmin ID`\n"
                "`/backup`, `/cleanup`\n"
                "Отправка `info.db` - импорт базы"
            )
    await update.message.reply_text(text, parse_mode="Markdown")

# --- Админские команды ---
async def admin_cmds_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команд addadmin/removeadmin/listadmins"""
    if not is_owner(update.effective_user.id):
        await update.message.reply_text("❌ Только для владельца")
        return

    cmd = update.message.text.split()[0].replace('/', '')
    args = context.args
    
    if cmd == 'listadmins':
        admins = get_all_admins()
        msg = "👥 *Список админов:*\n" + "\n".join([f"{i+1}. {u} (ID: {uid})" for i, (uid, u) in enumerate(admins)])
        await update.message.reply_text(msg, parse_mode='Markdown')
        return

    if not args:
        await update.message.reply_text(f"❌ Используй: `/{cmd} ID`", parse_mode='Markdown')
        return

    try:
        target_id = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ ID должен быть числом")
        return

    if cmd == 'addadmin':
        if add_admin_by_id(target_id, update.effective_user.id):
            await update.message.reply_text(f"✅ ID {target_id} добавлен.")
        else:
            await update.message.reply_text("❌ Ошибка добавления.")
    
    elif cmd == 'removeadmin':
        if remove_admin(target_id):
            await update.message.reply_text(f"✅ ID {target_id} удален.")
        else:
            await update.message.reply_text("❌ Ошибка (нельзя удалить владельца или не найден).")

# ==============================================================================
#                 ОБЪЕДИНЕННЫЕ ОБРАБОТЧИКИ СООБЩЕНИЙ
# ==============================================================================

async def unified_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает текстовые сообщения: и для архива, и для инфо-команд"""
    message = update.message
    if not message or not message.text:
        return
    
    text = message.text
    user = message.from_user
    chat_type = update.effective_chat.type
    
    # --- 1. ЛОГИКА АРХИВАЦИИ ---
    # Создаем тему и пересылаем сообщение, если это не приватный чат или если это просто текст
    # Но обычно архив работает лучше всего из лички с ботом
    topic_id = await get_or_create_topic(context, user.id, user.username, user.first_name)
    if topic_id:
        try:
            await context.bot.send_message(
                chat_id=ARCHIVE_GROUP_ID,
                message_thread_id=topic_id,
                text=f"💬 {text}"
            )
        except Exception as e:
            logger.error(f"Archive error: {e}")

    # --- 2. ЛОГИКА ИНФО-БОТА ---
    # Проверка на спец-команды инфо бота (!инфо, +инфо и т.д.)
    
    # Поиск
    if text.startswith('!инфо '):
        parts = text.split(' ', 1)
        if len(parts) > 1:
            username = parts[1].strip().lstrip('@')
            info_list = get_user_info(username)
            if info_list:
                safe_u = escape_markdown(username)
                resp = f"📋 *Инфо о @{safe_u}:*\n\n"
                for i, (_, txt, date) in enumerate(info_list, 1):
                    d_str = datetime.strptime(date, '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y')
                    resp += f"{i}. {escape_markdown(txt)} ({d_str})\n\n"
                await message.reply_text(resp, parse_mode='Markdown')
            else:
                await message.reply_text(f"ℹ️ Нет информации о {username}")
        return

    # Админские действия
    if is_admin(user.id):
        if text.startswith('+инфо '):
            parts = text.split(' ', 2)
            if len(parts) == 3:
                u, t = parts[1].lstrip('@'), parts[2]
                if add_user_info(u, t, user.id):
                    await message.reply_text(f"✅ Добавлено для @{u}")
            else:
                await message.reply_text("❌ Формат: `+инфо юзер текст`", parse_mode='Markdown')
            return
            
        if text.startswith('-инфо '):
            u = text.split(' ', 1)[1].strip().lstrip('@')
            if delete_user_info(u):
                await message.reply_text(f"✅ Всё удалено для @{u}")
            else:
                await message.reply_text("❌ Не найдено")
            return
            
        if text.startswith('--инфо '):
            parts = text.split()
            if len(parts) >= 3:
                u = parts[1].lstrip('@')
                try:
                    num = int(parts[2])
                    if delete_specific_info(u, num):
                        await message.reply_text(f"✅ Запись {num} удалена для @{u}")
                    else:
                        await message.reply_text("❌ Ошибка удаления")
                except ValueError:
                    await message.reply_text("❌ Номер должен быть числом")
            return

    # Меню текстом
    if text.lower() in ['меню', 'menu', 'start']:
        await message.reply_text("🎮 *Меню*", parse_mode='Markdown', 
                               reply_markup=get_main_menu_keyboard(chat_type, user.id))

async def unified_media_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка Фото, Голосовых, Кружочков для Архива"""
    message = update.message
    user = message.from_user
    topic_id = await get_or_create_topic(context, user.id, user.username, user.first_name)
    
    if not topic_id:
        return

    try:
        if message.photo:
            caption = f"📷 Фото\n\n{message.caption}" if message.caption else "📷 Фото"
            await context.bot.send_photo(chat_id=ARCHIVE_GROUP_ID, message_thread_id=topic_id,
                                       photo=message.photo[-1].file_id, caption=caption)
        elif message.voice:
            await context.bot.send_voice(chat_id=ARCHIVE_GROUP_ID, message_thread_id=topic_id,
                                       voice=message.voice.file_id, caption=f"🎤 Голосовое ({message.voice.duration}с)")
        elif message.video_note:
            await context.bot.send_video_note(chat_id=ARCHIVE_GROUP_ID, message_thread_id=topic_id,
                                            video_note=message.video_note.file_id)
            await context.bot.send_message(chat_id=ARCHIVE_GROUP_ID, message_thread_id=topic_id,
                                         text="⭕ Видео-кружок")
    except Exception as e:
        logger.error(f"Media archive error: {e}")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка документов (Импорт БД для владельца, иначе архив)"""
    message = update.message
    user = message.from_user
    doc = message.document
    
    # 1. Проверка на Импорт БД
    if is_owner(user.id) and update.effective_chat.type == 'private' and doc.file_name and doc.file_name.endswith('.db'):
        temp_path = f"temp_{doc.file_name}"
        f = await doc.get_file()
        await f.download_to_drive(temp_path)
        
        try:
            # Проверка
            t_conn = sqlite3.connect(temp_path)
            t_cur = t_conn.cursor()
            t_cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='info'")
            if not t_cur.fetchone(): raise Exception("Нет таблицы info")
            t_conn.close()
            
            # Бэкап и замена
            backup_database()
            shutil.copy2(temp_path, DB_FILE)
            os.remove(temp_path)
            await message.reply_text("✅ База данных успешно обновлена!")
            return
        except Exception as e:
            if os.path.exists(temp_path): os.remove(temp_path)
            await message.reply_text(f"❌ Ошибка БД: {e}")
            return

    # 2. Если не БД, отправляем в архив как файл
    topic_id = await get_or_create_topic(context, user.id, user.username, user.first_name)
    if topic_id:
        caption = f"📁 Файл: {doc.file_name}"
        if message.caption: caption += f"\n{message.caption}"
        try:
            await context.bot.send_document(chat_id=ARCHIVE_GROUP_ID, message_thread_id=topic_id,
                                          document=doc.file_id, caption=caption)
        except Exception as e:
            logger.error(f"Doc archive error: {e}")

# ==============================================================================
#                       CALLBACK HANDLERS (КНОПКИ)
# ==============================================================================
async def show_all_info_callback(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE):
    users = get_all_users()
    if not users:
        await safe_edit_message_text(query, "📭 База пуста", parse_mode='Markdown',
                                   reply_markup=get_back_keyboard(query.message.chat.type))
        return
    
    context.user_data['all_users'] = users
    context.user_data['current_page'] = 0
    await show_page(query, context)

async def show_page(query: CallbackQuery, context: ContextTypes.DEFAULT_TYPE):
    users = context.user_data.get('all_users', [])
    page = context.user_data.get('current_page', 0)
    items_per_page = 10
    
    page_users, total = get_paginated_users(users, page, items_per_page)
    
    msg = f"📋 *Список пользователей ({total})*\nСтраница {page+1}\n\n"
    start_num = page * items_per_page + 1
    
    for i, u in enumerate(page_users, start_num):
        infos = get_user_info(u)
        safe_u = escape_markdown(u)
        msg += f"{i}. 👤 *@{safe_u}*\n"
        for j, (_, txt, date) in enumerate(infos[:3], 1):
            d_str = datetime.strptime(date, '%Y-%m-%d %H:%M:%S').strftime('%d.%m')
            msg += f"   - {escape_markdown(txt)} ({d_str})\n"
        msg += "\n"
    
    kb = create_pagination_keyboard(users, page, query.message.chat.type)
    await safe_edit_message_text(query, msg, parse_mode='Markdown', reply_markup=kb)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    uid = query.from_user.id
    chat_type = query.message.chat.type
    
    if data == 'all_info':
        await show_all_info_callback(query, context)
        
    elif data.startswith('page_'):
        context.user_data['current_page'] = int(data.split('_')[1])
        await show_page(query, context)
        
    elif data == 'back_to_main':
        await safe_edit_message_text(query, "🎮 *Главное меню*", parse_mode='Markdown',
                                   reply_markup=get_main_menu_keyboard(chat_type, uid))
        
    # --- Админские кнопки ---
    elif data == 'management':
        if chat_type == 'private' and is_admin(uid):
            await safe_edit_message_text(query, "⚙️ *Управление*", parse_mode='Markdown',
                                       reply_markup=get_management_keyboard(uid))
    elif data == 'manage_admins':
        if is_owner(uid):
            await safe_edit_message_text(query, "👥 *Админы*", parse_mode='Markdown',
                                       reply_markup=get_admins_management_keyboard())
    elif data == 'create_backup':
        if is_owner(uid):
            bkp = backup_database()
            if bkp:
                with open(bkp, 'rb') as f:
                    await query.message.reply_document(f, caption="💾 Бэкап")
    elif data == 'cleanup':
        if is_owner(uid):
            c = cleanup_database()
            await query.message.reply_text(f"🧹 Удалено старых записей: {c}")
    elif data == 'stats':
        if is_admin(uid):
            # Простая статистика
            conn = sqlite3.connect(DB_FILE)
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM info")
            cnt = cur.fetchone()[0]
            conn.close()
            await safe_edit_message_text(query, f"📊 Записей всего: {cnt}", parse_mode='Markdown',
                                       reply_markup=get_back_keyboard(chat_type))
            
    # Подсказки для ввода ID
    elif data in ['add_admin_by_id', 'remove_admin_by_id']:
        cmd = "/addadmin" if "add" in data else "/removeadmin"
        await safe_edit_message_text(query, f"Отправьте: `{cmd} ID`", parse_mode='Markdown',
                                   reply_markup=get_back_keyboard(chat_type))
    elif data == 'list_admins':
        # Переадресация на текстовую команду для простоты вывода
        admins = get_all_admins()
        msg = "👥 *Админы:*\n" + "\n".join([f"- {u} (ID: {uid})" for uid, u in admins])
        await safe_edit_message_text(query, msg, parse_mode='Markdown', reply_markup=get_back_keyboard(chat_type))
        
    elif data == 'back_to_management':
        await safe_edit_message_text(query, "⚙️ *Управление*", parse_mode='Markdown',
                                   reply_markup=get_management_keyboard(uid))

async def tops_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /tops для вывода списка"""
    # Имитируем нажатие кнопки для переиспользования логики
    users = get_all_users()
    if not users:
        await update.message.reply_text("📭 Пусто")
        return
    context.user_data['all_users'] = users
    context.user_data['current_page'] = 0
    
    # Отправляем новое сообщение, так как это команда, а не коллбэк
    page_users, total = get_paginated_users(users, 0, 10)
    msg = f"📋 *Список ({total})*\nСтраница 1\n\n"
    start_num = 1
    for i, u in enumerate(page_users, start_num):
        infos = get_user_info(u)
        msg += f"{i}. @{escape_markdown(u)} ({len(infos)} зап.)\n"
    
    kb = create_pagination_keyboard(users, 0, update.effective_chat.type)
    await update.message.reply_text(msg, parse_mode='Markdown', reply_markup=kb)

# ==============================================================================
#                                   ЗАПУСК
# ==============================================================================
def main():
    init_db()
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Команды
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("mytopic", cmd_my_topic))
    app.add_handler(CommandHandler("tops", tops_command))
    
    # Админские команды
    app.add_handler(CommandHandler(["addadmin", "removeadmin", "listadmins", "backup", "cleanup"], admin_cmds_handler))
    
    # Текст и Медиа (Единые обработчики)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, unified_text_handler))
    app.add_handler(MessageHandler(filters.PHOTO | filters.VOICE | filters.VIDEO_NOTE, unified_media_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    # Callback (Кнопки)
    app.add_handler(CallbackQueryHandler(button_handler))
    
    print(f"🤖 Бот запущен! Архив: {ARCHIVE_GROUP_ID}, Владелец: {OWNER_ID}")
    app.run_polling()

if __name__ == "__main__":
    main()

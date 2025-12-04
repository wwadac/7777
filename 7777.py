import logging
import sqlite3
import re
import json
import os
import time
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    CommandHandler,
    filters,
    CallbackQueryHandler,
    ConversationHandler
)

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO,
    filename='bot.log'
)
logger = logging.getLogger(__name__)

# Константы
BOT_TOKEN = "8534057742:AAFfm2gswdz-b6STcrWcCdRfaToRDkPUu0A"
MAIN_OWNER_ID = 6893832048  # Главный владелец (только он может добавлять админов)
ADMINS_FILE = "admins.json"

# Состояния для ConversationHandler
ADD_ADMIN, CONFIRM_ADD_ADMIN = range(2)

# Загрузка администраторов из файла
def load_admins():
    if os.path.exists(ADMINS_FILE):
        try:
            with open(ADMINS_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    # Если файла нет или ошибка, создаем с главным владельцем
    admins = [MAIN_OWNER_ID]
    save_admins(admins)
    return admins

# Сохранение администраторов в файл
def save_admins(admins):
    with open(ADMINS_FILE, 'w') as f:
        json.dump(admins, f)

# Получение списка администраторов
def get_admins():
    return load_admins()

# Проверка является ли пользователь администратором бота
def is_bot_admin(user_id: int) -> bool:
    return user_id in get_admins()

# Проверка является ли пользователь главным владельцем
def is_main_owner(user_id: int) -> bool:
    return user_id == MAIN_OWNER_ID

# Добавление нового администратора
def add_admin(new_admin_id: int) -> bool:
    admins = get_admins()
    if new_admin_id not in admins:
        admins.append(new_admin_id)
        save_admins(admins)
        return True
    return False

# Удаление администратора
def remove_admin(admin_id: int) -> bool:
    admins = get_admins()
    if admin_id in admins and admin_id != MAIN_OWNER_ID:
        admins.remove(admin_id)
        save_admins(admins)
        return True
    return False

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect("info.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_info (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            user_id INTEGER,
            text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

# Сохранение данных
def save_info(username: str, first_name: str, last_name: str, user_id: int, text: str):
    conn = sqlite3.connect("info.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO user_info (username, first_name, last_name, user_id, text) 
        VALUES (?, ?, ?, ?, ?)
    """, (username, first_name, last_name, user_id, text))
    conn.commit()
    conn.close()

# Получение всех записей
def get_all_info():
    conn = sqlite3.connect("info.db")
    cursor = conn.cursor()
    cursor.execute("SELECT username, first_name, last_name, user_id, text FROM user_info ORDER BY username")
    rows = cursor.fetchall()
    conn.close()
    return rows

# Получение информации о пользователе
def get_user_info_by_username(username: str):
    conn = sqlite3.connect("info.db")
    cursor = conn.cursor()
    cursor.execute("SELECT username, first_name, last_name, user_id, text FROM user_info WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    return row

def get_user_info_by_id(user_id: int):
    conn = sqlite3.connect("info.db")
    cursor = conn.cursor()
    cursor.execute("SELECT username, first_name, last_name, user_id, text FROM user_info WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row

# Удаление информации о пользователе
def delete_user_info(username: str):
    conn = sqlite3.connect("info.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM user_info WHERE username = ?", (username,))
    deleted_count = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted_count

# Проверка админских прав в группе (для +инфо, -инфо)
async def is_admin(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> bool:
    try:
        admins = await context.bot.get_chat_administrators(chat_id)
        admin_ids = [admin.user.id for admin in admins]
        return user_id in admin_ids
    except Exception as e:
        logger.error(f"Ошибка при проверке прав администратора: {e}")
        return False

# ========== КОМАНДЫ ДЛЯ ВЛАДЕЛЬЦЕВ БОТА ==========

# Команда /admin - панель администратора
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_bot_admin(user_id):
        await update.message.reply_text("❌ Эта команда доступна только владельцам бота!")
        return
    
    keyboard = [
        [InlineKeyboardButton("📦 Экспорт БД", callback_data="export_db")],
        [InlineKeyboardButton("📋 Экспорт логов", callback_data="export_logs")],
        [InlineKeyboardButton("🔄 Импорт БД", callback_data="import_db_info")],
        [InlineKeyboardButton("👥 Список админов", callback_data="list_admins")],
    ]
    
    if is_main_owner(user_id):
        keyboard.append([InlineKeyboardButton("➕ Добавить админа", callback_data="add_admin_start")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🛠️ **Панель администратора**\n\n"
        "Выберите действие:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

# Обработчик кнопок панели администратора
async def admin_panel_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    if not is_bot_admin(user_id):
        await query.edit_message_text("❌ Доступ запрещен!")
        return
    
    if query.data == "export_db":
        await export_db_command(query, context)
    elif query.data == "export_logs":
        await export_logs_command(query, context)
    elif query.data == "import_db_info":
        await import_db_info(query, context)
    elif query.data == "list_admins":
        await list_admins_command(query, context)
    elif query.data == "add_admin_start":
        if is_main_owner(user_id):
            await add_admin_start(query, context)
        else:
            await query.edit_message_text("❌ Только главный владелец может добавлять админов!")

# Экспорт базы данных
async def export_db_command(query, context):
    if not os.path.exists("info.db"):
        await query.edit_message_text("❌ База данных не найдена!")
        return
    
    try:
        with open("info.db", "rb") as db_file:
            await context.bot.send_document(
                chat_id=query.message.chat_id,
                document=db_file,
                filename="info.db",
                caption="📦 База данных бота"
            )
        await query.edit_message_text("✅ База данных отправлена!")
    except Exception as e:
        logger.error(f"Ошибка при экспорте БД: {e}")
        await query.edit_message_text("❌ Ошибка при отправке базы данных!")

# Экспорт логов
async def export_logs_command(query, context):
    if not os.path.exists("bot.log"):
        await query.edit_message_text("❌ Файл логов не найден!")
        return
    
    try:
        with open("bot.log", "rb") as log_file:
            await context.bot.send_document(
                chat_id=query.message.chat_id,
                document=log_file,
                filename="bot.log",
                caption="📋 Логи бота"
            )
        await query.edit_message_text("✅ Логи отправлены!")
    except Exception as e:
        logger.error(f"Ошибка при экспорте логов: {e}")
        await query.edit_message_text("❌ Ошибка при отправке логов!")

# Информация об импорте БД
async def import_db_info(query, context):
    await query.edit_message_text(
        "🔄 **Импорт базы данных**\n\n"
        "Для импорта базы данных:\n"
        "1. Отправьте файл `info.db` в этот чат\n"
        "2. Бот автоматически его обработает\n"
        "3. После успешного импорта бот перезагрузится\n\n"
        "⚠️ **Внимание:** Текущая база данных будет заменена!",
        parse_mode="Markdown"
    )

# Список админов
async def list_admins_command(query, context):
    admins = get_admins()
    
    admin_list = "👑 **Владельцы бота:**\n\n"
    for admin_id in admins:
        try:
            user = await context.bot.get_chat(admin_id)
            name = f"@{user.username}" if user.username else f"{user.first_name or 'User'}"
            owner_type = "👑 Главный" if admin_id == MAIN_OWNER_ID else "👤 Админ"
            admin_list += f"• {name} (ID: `{admin_id}`) - {owner_type}\n"
        except:
            owner_type = "👑 Главный" if admin_id == MAIN_OWNER_ID else "👤 Админ"
            admin_list += f"• ID: `{admin_id}` - {owner_type}\n"
    
    keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_admin")]]
    
    await query.edit_message_text(
        admin_list,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

# Добавление админа - начало
async def add_admin_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    if not is_main_owner(user_id):
        await query.edit_message_text("❌ Только главный владелец может добавлять админов!")
        return ConversationHandler.END
    
    await query.edit_message_text(
        "➕ **Добавление администратора**\n\n"
        "Отправьте ID пользователя, которого хотите добавить.\n"
        "Для отмены отправьте /cancel",
        parse_mode="Markdown"
    )
    return ADD_ADMIN

# Добавление админа - обработка ID
async def add_admin_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_main_owner(user_id):
        await update.message.reply_text("❌ Только главный владелец может добавлять админов!")
        return ConversationHandler.END
    
    try:
        new_admin_id = int(update.message.text.strip())
        
        if new_admin_id == MAIN_OWNER_ID:
            await update.message.reply_text("❌ Этот пользователь уже является главным владельцем!")
            return ConversationHandler.END
        
        if new_admin_id in get_admins():
            await update.message.reply_text("❌ Этот пользователь уже является администратором!")
            return ConversationHandler.END
        
        # Сохраняем во временные данные
        context.user_data['new_admin_id'] = new_admin_id
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Да", callback_data="confirm_add"),
                InlineKeyboardButton("❌ Нет", callback_data="cancel_add")
            ]
        ]
        
        await update.message.reply_text(
            f"❓ Добавить пользователя с ID `{new_admin_id}` в администраторы?",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        
        return CONFIRM_ADD_ADMIN
        
    except ValueError:
        await update.message.reply_text("❌ Неверный формат ID. Отправьте числовой ID.")
        return ADD_ADMIN

# Подтверждение добавления админа
async def confirm_add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "confirm_add":
        new_admin_id = context.user_data.get('new_admin_id')
        
        if add_admin(new_admin_id):
            await query.edit_message_text(f"✅ Пользователь с ID `{new_admin_id}` добавлен в администраторы!")
        else:
            await query.edit_message_text("❌ Ошибка при добавлении администратора!")
    else:
        await query.edit_message_text("❌ Добавление администратора отменено!")
    
    return ConversationHandler.END

# Отмена добавления админа
async def cancel_add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Добавление администратора отменено!")
    return ConversationHandler.END

# Кнопка "Назад" в панели админа
async def back_to_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    
    if not is_bot_admin(user_id):
        await query.edit_message_text("❌ Доступ запрещен!")
        return
    
    keyboard = [
        [InlineKeyboardButton("📦 Экспорт БД", callback_data="export_db")],
        [InlineKeyboardButton("📋 Экспорт логов", callback_data="export_logs")],
        [InlineKeyboardButton("🔄 Импорт БД", callback_data="import_db_info")],
        [InlineKeyboardButton("👥 Список админов", callback_data="list_admins")],
    ]
    
    if is_main_owner(user_id):
        keyboard.append([InlineKeyboardButton("➕ Добавить админа", callback_data="add_admin_start")])
    
    await query.edit_message_text(
        "🛠️ **Панель администратора**\n\n"
        "Выберите действие:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

# ========== ОБРАБОТКА ФАЙЛОВ ДЛЯ ИМПОРТА БД ==========

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.document:
        return
    
    user_id = update.effective_user.id
    
    # Проверяем, что отправитель - администратор бота
    if not is_bot_admin(user_id):
        await update.message.reply_text("❌ Только владельцы бота могут импортировать базу данных!")
        return
    
    document = update.message.document
    
    # Проверяем, что это файл базы данных
    if document.file_name != "info.db":
        await update.message.reply_text(
            "📁 Для импорта базы данных отправьте файл с именем `info.db`",
            parse_mode="Markdown"
        )
        return
    
    await process_db_import(update, context, document)

async def process_db_import(update: Update, context: ContextTypes.DEFAULT_TYPE, document):
    user_id = update.effective_user.id
    chat_id = update.message.chat_id
    
    try:
        # Уведомляем о начале загрузки
        status_msg = await update.message.reply_text("⬇️ Загрузка файла базы данных...")
        
        # Создаем временную папку
        temp_dir = "temp_import"
        os.makedirs(temp_dir, exist_ok=True)
        
        # Скачиваем файл
        file = await context.bot.get_file(document.file_id)
        temp_path = f"{temp_dir}/info_{int(time.time())}.db"
        await file.download_to_drive(temp_path)
        
        await status_msg.edit_text("🔍 Проверка файла базы данных...")
        
        # Проверяем валидность базы данных
        try:
            conn = sqlite3.connect(temp_path)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM user_info")
            count = cursor.fetchone()[0]
            cursor.execute("PRAGMA table_info(user_info)")
            columns = cursor.fetchall()
            conn.close()
            
            # Проверяем структуру таблицы
            expected_columns = ['id', 'username', 'first_name', 'last_name', 'user_id', 'text', 'created_at']
            actual_columns = [col[1] for col in columns]
            
            # Проверяем наличие основных столбцов
            required_columns = ['username', 'first_name', 'last_name', 'user_id', 'text']
            column_names = [col[1] for col in columns]
            
            missing_columns = [col for col in required_columns if col not in column_names]
            
            if missing_columns:
                await status_msg.edit_text(f"❌ Неверная структура базы данных! Отсутствуют столбцы: {missing_columns}")
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                try:
                    os.rmdir(temp_dir)
                except:
                    pass
                return
            
            await status_msg.edit_text(f"✅ Файл проверен. Записей: {count}\n\nСоздаю резервную копию...")
            
            # Создаем резервную копию текущей БД
            if os.path.exists("info.db"):
                backup_name = f"info.db.backup_{int(time.time())}"
                os.rename("info.db", backup_name)
                logger.info(f"Создана резервная копия: {backup_name}")
            
            # Заменяем текущую БД
            os.rename(temp_path, "info.db")
            
            # Очищаем временную папку
            try:
                os.rmdir(temp_dir)
            except:
                pass  # Игнорируем если папка не пустая
            
            await status_msg.edit_text(
                f"✅ База данных успешно импортирована!\n"
                f"📊 Записей в базе: {count}\n\n"
                f"🔄 Бот продолжает работу с новой базой данных."
            )
            
            logger.info(f"База данных импортирована пользователем {user_id}. Записей: {count}")
            
        except sqlite3.Error as e:
            await status_msg.edit_text(f"❌ Ошибка в базе данных: {str(e)}")
            if os.path.exists(temp_path):
                os.remove(temp_path)
            try:
                os.rmdir(temp_dir)
            except:
                pass
            logger.error(f"Ошибка при импорте БД: {e}")
            
    except Exception as e:
        logger.error(f"Ошибка при импорте БД: {e}")
        await update.message.reply_text("❌ Произошла ошибка при импорте базы данных!")

# ========== ОСНОВНЫЕ КОМАНДЫ БОТА ==========

# Команда /tops - ДОСТУПНА ВСЕМ!
async def tops(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        logger.info(f"Получена команда /tops от пользователя {update.effective_user.id}")
        
        # Проверяем, что команда пришла в групповом чате
        if update.effective_chat.type not in ['group', 'supergroup']:
            await update.message.reply_text("❌ Эта команда доступна только в группах!")
            return
            
        rows = get_all_info()
        if not rows:
            await update.message.reply_text("📭 Список пуст.")
            return

        response = "📋 Список информации:\n\n"
        for username, first_name, last_name, user_id, text in rows:
            if username:
                display_name = f"@{username}"
            elif first_name and last_name:
                display_name = f"{first_name} {last_name}"
            elif first_name:
                display_name = first_name
            else:
                display_name = f"id{user_id}"
            
            if user_id and user_id != 0:
                user_link = f"[{display_name}](tg://user?id={user_id})"
            else:
                user_link = display_name
            
            user_id_display = "↔" if user_id == 0 else user_id
            
            response += f"{user_link} | {user_id_display} | {text}\n"

        if len(response) > 4096:
            parts = []
            current_part = ""
            for line in response.split('\n'):
                if len(current_part) + len(line) + 1 > 4096:
                    parts.append(current_part)
                    current_part = line + '\n'
                else:
                    current_part += line + '\n'
            
            if current_part:
                parts.append(current_part)
                
            for i, part in enumerate(parts):
                if i == 0:
                    await update.message.reply_text(part, parse_mode="Markdown", disable_web_page_preview=True)
                else:
                    await update.message.reply_text(f"📋 Продолжение ({i+1}/{len(parts)}):\n\n{part}", 
                                                  parse_mode="Markdown", 
                                                  disable_web_page_preview=True)
        else:
            await update.message.reply_text(response, parse_mode="Markdown", disable_web_page_preview=True)
            
    except Exception as e:
        logger.error(f"Ошибка в команде /tops: {e}")
        await update.message.reply_text("❌ Произошла ошибка при выполнении команды.")

# Обработчик +инфо - ТОЛЬКО ДЛЯ АДМИНОВ ГРУППЫ
async def add_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    message = update.message.text
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if not await is_admin(context, chat_id, user_id):
        await update.message.reply_text("❌ Только админы могут использовать эту команду!")
        return

    match = re.match(r"^\+\s*инфо\s+(@?\w+)\s+(.+)$", message, re.DOTALL)
    if not match:
        await update.message.reply_text("📝 Используйте формат: `+инфо @username текст`", parse_mode="Markdown")
        return

    target = match.group(1).lower()
    info_text = match.group(2).strip()
    
    if target.startswith('@'):
        target = target[1:]
    
    target_user_id = 0
    first_name = ""
    last_name = ""
    actual_username = target

    try:
        try:
            chat_member = await context.bot.get_chat_member(chat_id, f"@{target}")
            target_user_id = chat_member.user.id
            actual_username = chat_member.user.username or target
            first_name = chat_member.user.first_name or ""
            last_name = chat_member.user.last_name or ""
        except:
            if target.isdigit():
                chat_member = await context.bot.get_chat_member(chat_id, int(target))
                target_user_id = chat_member.user.id
                actual_username = chat_member.user.username or f"id{target}"
                first_name = chat_member.user.first_name or ""
                last_name = chat_member.user.last_name or ""
    except Exception as e:
        logging.warning(f"Не удалось получить информацию для {target}: {e}")

    existing_info = get_user_info_by_username(actual_username)
    if not existing_info and target_user_id != 0:
        existing_info = get_user_info_by_id(target_user_id)
    
    if existing_info:
        await update.message.reply_text(f"ℹ️ Информация о @{actual_username} уже есть. Используйте `-инфо @{actual_username}` чтобы удалить.")
        return

    save_info(actual_username, first_name, last_name, target_user_id, info_text)
    await update.message.reply_text(f"✅ Информация для @{actual_username} сохранена: {info_text}")

# Обработчик -инфо - ТОЛЬКО ДЛЯ АДМИНОВ ГРУППЫ
async def remove_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    message = update.message.text
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if not await is_admin(context, chat_id, user_id):
        await update.message.reply_text("❌ Только админы могут использовать эту команду!")
        return

    match = re.match(r"^-\s*инфо\s+@?(\w+)$", message)
    if not match:
        await update.message.reply_text("📝 Используйте формат: `-инфо @username`", parse_mode="Markdown")
        return

    target_username = match.group(1).lower()

    existing_info = get_user_info_by_username(target_username)
    if not existing_info:
        await update.message.reply_text(f"ℹ️ Информации о @{target_username} не найдено.")
        return

    deleted_count = delete_user_info(target_username)
    if deleted_count > 0:
        await update.message.reply_text(f"🗑️ Информация о @{target_username} удалена.")
    else:
        await update.message.reply_text(f"⚠️ Не удалось удалить информацию о @{target_username}.")

# Обработчик !инфо - ДОСТУПНА ВСЕМ!
async def get_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    message = update.message.text
    
    match = re.match(r"^!\s*инфо\s+@?(\w+)$", message)
    if not match:
        await update.message.reply_text("📝 Используйте формат: `!инфо @username`", parse_mode="Markdown")
        return

    target_username = match.group(1).lower()

    user_info = get_user_info_by_username(target_username)
    
    if not user_info:
        await update.message.reply_text(f"❌ Информации о @{target_username} не найдено.")
        return

    username, first_name, last_name, user_id, text = user_info
    
    if username:
        display_name = f"@{username}"
    elif first_name and last_name:
        display_name = f"{first_name} {last_name}"
    elif first_name:
        display_name = first_name
    else:
        display_name = f"id{user_id}"
    
    if user_id and user_id != 0:
        user_link = f"[{display_name}](tg://user?id={user_id})"
    else:
        user_link = display_name
    
    user_id_display = "↔" if user_id == 0 else user_id
    
    response = f"👤 {user_link} | {user_id_display} | {text}"
    await update.message.reply_text(response, parse_mode="Markdown", disable_web_page_preview=True)

# Основной обработчик сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    message = update.message.text.strip()
    
    if message.startswith('+инфо'):
        await add_info(update, context)
    elif message.startswith('-инфо'):
        await remove_info(update, context)
    elif message.startswith('!инфо'):
        await get_info(update, context)

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if is_bot_admin(user_id):
        keyboard = [[InlineKeyboardButton("🛠️ Панель администратора", callback_data="admin_panel")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "👋 Привет! Я бот для управления информацией о пользователях.\n\n"
            "📋 **Основные команды:**\n"
            "/tops - Показать весь список информации\n"
            "+инфо @username текст - Добавить информацию (только для админов группы)\n"
            "-инфо @username - Удалить информацию (только для админов группы)\n"
            "!инфо @username - Узнать информацию\n\n"
            "🛠️ **Для владельцев бота доступна панель администратора:**",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            "👋 Привет! Я бот для управления информацией о пользователях.\n\n"
            "📋 **Основные команды:**\n"
            "/tops - Показать весь список информации\n"
            "!инфо @username - Узнать информацию о пользователе\n\n"
            "❓ Для добавления или удаления информации обратитесь к администраторам группы."
        )

# Команда /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """
📋 **Доступные команды:**

/tops - показать весь список информации
+инфо - добавить информацию о пользователе (только для админов группы)
-инфо - удалить информацию о пользователе (только для админов группы)
!инфо - узнать информацию о конкретном пользователе

🛠️ **Администраторам бота также доступно:**
/admin - панель администратора бота
    """
    await update.message.reply_text(help_text, parse_mode="Markdown")

# Главная функция
def main():
    # Инициализация базы данных
    init_db()
    
    # Загружаем администраторов
    admins = get_admins()
    logger.info(f"Загружены администраторы: {admins}")
    
    # Создание приложения
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # ConversationHandler для добавления админа с исправленными настройками
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_admin_start, pattern="^add_admin_start$")],
        states={
            ADD_ADMIN: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_admin_process),
                CallbackQueryHandler(back_to_admin_panel, pattern="^back_to_admin$")
            ],
            CONFIRM_ADD_ADMIN: [
                CallbackQueryHandler(confirm_add_admin, pattern="^(confirm_add|cancel_add)$"),
                CallbackQueryHandler(back_to_admin_panel, pattern="^back_to_admin$")
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cancel_add_admin),
            CallbackQueryHandler(back_to_admin_panel, pattern="^back_to_admin$")
        ],
        per_message=True
    )

    # Регистрация обработчиков
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("tops", tops))
    
    # Обработчики для админ-панели
    app.add_handler(CallbackQueryHandler(admin_panel_button, pattern="^(export_db|export_logs|import_db_info|list_admins|admin_panel)$"))
    app.add_handler(CallbackQueryHandler(back_to_admin_panel, pattern="^back_to_admin$"))
    app.add_handler(conv_handler)
    
    # Обработчик документов (для импорта БД)
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    # Обработчик сообщений
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("=" * 50)
    print("🤖 Бот запущен...")
    print("=" * 50)
    print(f"Главный владелец: {MAIN_OWNER_ID}")
    print(f"👥 Администраторы: {admins}")
    print("\n📋 Основные команды:")
    print("/help - Справка по командам")
    print("/tops - Весь список информации (доступно всем)")
    print("+инфо @ник текст - добавить информацию (только для админов группы)")
    print("-инфо @ник - удалить информацию (только для админов группы)")
    print("!инфо @ник - узнать информацию (доступно всем)")
    print("\n🛠️ Для импорта БД: отправьте файл info.db в чат с ботом (только для владельцев бота)")
    print("📝 Логи сохраняются в файл bot.log")
    print("=" * 50)
    
    # Запуск бота
    app.run_polling()

if __name__ == "__main__":
    main()

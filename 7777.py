import logging
import sqlite3
import os
import shutil
from datetime import datetime
from typing import Dict, List
import apscheduler
from apscheduler.schedulers.background import BackgroundScheduler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, 
    CommandHandler, 
    MessageHandler, 
    CallbackQueryHandler, 
    ContextTypes, 
    ConversationHandler,
    filters
)
from telegram.error import BadRequest

# ========== КОНФИГУРАЦИЯ ==========
TOKEN = "8534057742:AAFfm2gswdz-b6STcrWcCdRfaToRDkPUu0A"
ADMIN_IDS = ["6893832048"]  # ТОЛЬКО ВАШ ID
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

# Состояния для ConversationHandler
SELECTING_ACTION, TYPING_NICKNAME, TYPING_INFO, CONFIRM_DELETE = range(4)

# ========== БАЗА ДАННЫХ ==========
def init_db():
    """Инициализация базы данных."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS info (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT,
            info_text TEXT NOT NULL,
            added_by INTEGER NOT NULL,
            added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_username ON info(username)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_id ON info(user_id)')
    
    conn.commit()
    conn.close()

def cleanup_old_backups():
    """Очистка старых резервных копий (оставляет только последние 10)."""
    try:
        if not os.path.exists(BACKUP_DIR):
            os.makedirs(BACKUP_DIR)
            
        backups = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith('info.db.backup_')])
        
        if len(backups) > 10:
            for old_backup in backups[:-10]:
                os.remove(os.path.join(BACKUP_DIR, old_backup))
                logger.info(f"Удален старый бэкап: {old_backup}")
    except Exception as e:
        logger.error(f"Ошибка при очистке бэкапов: {e}")

def cleanup_database():
    """Очистка базы данных от старых записей (старше 30 дней)."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM info WHERE added_date < datetime('now', '-30 days')")
        deleted_count = cursor.rowcount
        
        conn.commit()
        conn.close()
        
        logger.info(f"Очистка базы данных завершена. Очищено записей: {deleted_count}")
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
        backup_file = os.path.join(BACKUP_DIR, f"info.db.backup_{timestamp}")
        shutil.copy2(DB_FILE, backup_file)
        
        logger.info(f"Создана резервная копия: info.db.backup_{timestamp}")
        return f"info.db.backup_{timestamp}"
    except Exception as e:
        logger.error(f"Ошибка при создании бэкапа: {e}")
        return None

def import_database_from_file(file_path: str) -> int:
    """Импорт базы данных из файла."""
    try:
        # Создаем резервную копию текущей БД
        backup_name = backup_database()
        
        import sqlite3
        conn = sqlite3.connect(DB_FILE)
        conn.close()
        
        shutil.copy2(file_path, DB_FILE)
        
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM info")
        count = cursor.fetchone()[0]
        conn.close()
        
        logger.info(f"База данных импортирована. Записей: {count}")
        return count
    except Exception as e:
        logger.error(f"Ошибка при импорте БД: {e}")
        
        if backup_name and os.path.exists(os.path.join(BACKUP_DIR, backup_name)):
            shutil.copy2(os.path.join(BACKUP_DIR, backup_name), DB_FILE)
            logger.info(f"Восстановлен из бэкапа: {backup_name}")
        
        raise e

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def is_owner(user_id: int) -> bool:
    """Проверяет, является ли пользователь владельцем."""
    return str(user_id) in ADMIN_IDS

def get_user_info(username: str) -> List[Dict]:
    """Получение информации о пользователе."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        username_clean = username.lstrip('@').lower()
        
        cursor.execute('''
            SELECT username, info_text, added_date 
            FROM info 
            WHERE LOWER(username) = ? 
            ORDER BY added_date DESC
        ''', (username_clean,))
        
        results = cursor.fetchall()
        conn.close()
        
        return [
            {
                'username': row[0],
                'info_text': row[1],
                'added_date': row[2]
            }
            for row in results
        ]
    except Exception as e:
        logger.error(f"Ошибка при получении информации: {e}")
        return []

def add_user_info(username: str, info_text: str, added_by: int) -> bool:
    """Добавление информации о пользователе."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        user_id = 0
        username_clean = username.lstrip('@')
        
        cursor.execute('''
            INSERT INTO info (user_id, username, info_text, added_by)
            VALUES (?, ?, ?, ?)
        ''', (user_id, username_clean, info_text, added_by))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Ошибка при добавлении информации: {e}")
        return False

def delete_user_info(username: str) -> bool:
    """Удаление информации о пользователе."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        username_clean = username.lstrip('@').lower()
        
        cursor.execute('DELETE FROM info WHERE LOWER(username) = ?', (username_clean,))
        deleted_count = cursor.rowcount
        
        conn.commit()
        conn.close()
        
        logger.info(f"Удалено записей для {username}: {deleted_count}")
        return deleted_count > 0
    except Exception as e:
        logger.error(f"Ошибка при удалении информации: {e}")
        return False

def get_all_info() -> List[Dict]:
    """Получение всей информации из базы."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT username, info_text, added_date 
            FROM info 
            ORDER BY username, added_date DESC
        ''')
        
        results = cursor.fetchall()
        conn.close()
        
        return [
            {
                'username': row[0],
                'info_text': row[1],
                'added_date': row[2]
            }
            for row in results
        ]
    except Exception as e:
        logger.error(f"Ошибка при получении всей информации: {e}")
        return []

# ========== ОБРАБОТЧИКИ КОМАНД ==========
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start."""
    await update.message.reply_text(
        "👋 Привет! Я бот для хранения информации о пользователях.\n\n"
        "📋 Основные команды:\n"
        "/help - Справка по командам\n"
        "/tops - Весь список информации\n\n"
        "📝 Для работы в группах:\n"
        "+инфо @ник текст - добавить информацию\n"
        "-инфо @ник - удалить информацию\n"
        "!инфо @ник - узнать информацию\n\n"
        "🛠️ Для импорта БД: отправьте файл info.db в чат с ботом"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /help."""
    help_text = (
        "📖 **Справка по командам:**\n\n"
        "👑 **Команды для владельцев:**\n"
        "/stats - Статистика базы данных\n"
        "/backup - Создать резервную копию БД\n"
        "/cleanup - Очистить старые записи\n\n"
        "👥 **Команды для всех:**\n"
        "/start - Начало работы\n"
        "/help - Эта справка\n"
        "/tops - Показать всю информацию\n"
        "!инфо @ник - Найти информацию о пользователе\n\n"
        "📝 **Работа в группах:**\n"
        "+инфо @ник текст - добавить информацию\n"
        "-инфо @ник - удалить информацию\n\n"
        "💾 **Импорт БД (только для владельца):**\n"
        "Отправьте файл info.db в чат для импорта\n"
        "/backup - получить резервную копию БД"
    )
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def tops_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /tops - показывает всю информацию."""
    try:
        logger.info(f"Получена команда /tops от пользователя {update.effective_user.id}")
        
        all_info = get_all_info()
        
        if not all_info:
            await update.message.reply_text("📭 База данных пуста.")
            return
        
        grouped_info = {}
        for item in all_info:
            username = item['username']
            if username not in grouped_info:
                grouped_info[username] = []
            grouped_info[username].append(item)
        
        message_parts = []
        for username, items in grouped_info.items():
            message_parts.append(f"👤 **@{username}**")
            for i, item in enumerate(items, 1):
                date_str = datetime.strptime(item['added_date'], '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y')
                message_parts.append(f"  {i}. {item['info_text']} ({date_str})")
            message_parts.append("")
        
        full_message = "\n".join(message_parts)
        max_length = 4000
        
        if len(full_message) > max_length:
            parts = []
            current_part = ""
            
            for line in message_parts:
                if len(current_part) + len(line) + 1 > max_length:
                    parts.append(current_part)
                    current_part = line + "\n"
                else:
                    current_part += line + "\n"
            
            if current_part:
                parts.append(current_part)
            
            for i, part in enumerate(parts, 1):
                if i == 1:
                    await update.message.reply_text(f"📋 Вся информация (часть {i}/{len(parts)}):\n\n{part}", parse_mode='Markdown')
                else:
                    await update.message.reply_text(f"📋 (часть {i}/{len(parts)})\n\n{part}", parse_mode='Markdown')
        else:
            await update.message.reply_text(f"📋 Вся информация:\n\n{full_message}", parse_mode='Markdown')
            
    except Exception as e:
        logger.error(f"Ошибка в /tops: {e}")
        await update.message.reply_text("❌ Произошла ошибка при получении информации.")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /stats - статистика базы данных."""
    try:
        user_id = update.effective_user.id
        if not is_owner(user_id):
            await update.message.reply_text("❌ Эта команда доступна только владельцу бота.")
            return
        
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM info")
        total_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(DISTINCT username) FROM info")
        unique_users = cursor.fetchone()[0]
        
        cursor.execute("SELECT MIN(added_date), MAX(added_date) FROM info")
        date_range = cursor.fetchone()
        
        conn.close()
        
        message = f"📊 **Статистика базы данных:**\n\n"
        message += f"• Всего записей: {total_count}\n"
        message += f"• Уникальных пользователей: {unique_users}\n"
        
        if date_range[0] and date_range[1]:
            first_date = datetime.strptime(date_range[0], '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y')
            last_date = datetime.strptime(date_range[1], '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y')
            message += f"• Период данных: с {first_date} по {last_date}\n"
        
        if os.path.exists(BACKUP_DIR):
            backups = os.listdir(BACKUP_DIR)
            message += f"\n💾 **Резервные копии:** {len(backups)} файлов\n"
        
        await update.message.reply_text(message, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Ошибка в /stats: {e}")
        await update.message.reply_text("❌ Произошла ошибка при получении статистики.")

async def backup_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /backup - создает и отправляет резервную копию."""
    try:
        user_id = update.effective_user.id
        if not is_owner(user_id):
            await update.message.reply_text("❌ Эта команда доступна только владельцу бота.")
            return
        
        backup_name = backup_database()
        
        if backup_name:
            backup_path = os.path.join(BACKUP_DIR, backup_name)
            
            with open(backup_path, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=backup_name,
                    caption=f"💾 Резервная копия создана: {backup_name}"
                )
        else:
            await update.message.reply_text("❌ Не удалось создать резервную копию.")
            
    except Exception as e:
        logger.error(f"Ошибка в /backup: {e}")
        await update.message.reply_text("❌ Произошла ошибка при создании резервной копии.")

async def cleanup_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /cleanup - очистка старых записей."""
    try:
        user_id = update.effective_user.id
        if not is_owner(user_id):
            await update.message.reply_text("❌ Эта команда доступна только владельцу бота.")
            return
        
        deleted_count = cleanup_database()
        cleanup_old_backups()
        
        await update.message.reply_text(
            f"🧹 Очистка завершена!\n"
            f"• Удалено записей: {deleted_count}\n"
            f"• Очищены старые резервные копии"
        )
        
    except Exception as e:
        logger.error(f"Ошибка в /cleanup: {e}")
        await update.message.reply_text("❌ Произошла ошибка при очистке.")

# ========== ОБРАБОТЧИКИ СООБЩЕНИЙ ==========
async def handle_info_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды !инфо @ник."""
    try:
        text = update.message.text.strip()
        
        if not text.startswith('!инфо '):
            return
        
        parts = text.split(' ', 2)
        if len(parts) < 2:
            await update.message.reply_text("❌ Формат: !инфо @никнейм")
            return
        
        username = parts[1]
        
        info_list = get_user_info(username)
        
        if not info_list:
            await update.message.reply_text(f"ℹ️ Информация о @{username.lstrip('@')} не найдена.")
            return
        
        response = f"📋 Информация о @{username.lstrip('@')}:\n\n"
        
        for i, info in enumerate(info_list, 1):
            date_str = datetime.strptime(info['added_date'], '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y %H:%M')
            response += f"{i}. {info['info_text']}\n   📅 {date_str}\n\n"
        
        await update.message.reply_text(response)
        
    except Exception as e:
        logger.error(f"Ошибка в handle_info_command: {e}")
        await update.message.reply_text("❌ Произошла ошибка при поиске информации.")

async def handle_add_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды +инфо @ник текст."""
    try:
        user_id = update.effective_user.id
        
        text = update.message.text.strip()
        
        if not text.startswith('+инфо '):
            return
        
        parts = text.split(' ', 2)
        if len(parts) < 3:
            await update.message.reply_text("❌ Формат: +инфо @никнейм текст_информации")
            return
        
        username = parts[1]
        info_text = parts[2]
        
        if not username.startswith('@'):
            await update.message.reply_text("❌ Укажите username с @ (например: @username)")
            return
        
        success = add_user_info(username, info_text, user_id)
        
        if success:
            await update.message.reply_text(f"✅ Информация о @{username.lstrip('@')} успешно добавлена!")
        else:
            await update.message.reply_text("❌ Не удалось добавить информацию.")
            
    except Exception as e:
        logger.error(f"Ошибка в handle_add_info: {e}")
        await update.message.reply_text("❌ Произошла ошибка при добавлении информации.")

async def handle_delete_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды -инфо @ник."""
    try:
        user_id = update.effective_user.id
        
        text = update.message.text.strip()
        
        if not text.startswith('-инфо '):
            return
        
        parts = text.split(' ', 1)
        if len(parts) < 2:
            await update.message.reply_text("❌ Формат: -инфо @никнейм")
            return
        
        username = parts[1]
        
        if not username.startswith('@'):
            await update.message.reply_text("❌ Укажите username с @ (например: @username)")
            return
        
        success = delete_user_info(username)
        
        if success:
            await update.message.reply_text(f"✅ Информация о @{username.lstrip('@')} успешно удалена!")
        else:
            await update.message.reply_text(f"ℹ️ Информация о @{username.lstrip('@')} не найдена.")
            
    except Exception as e:
        logger.error(f"Ошибка в handle_delete_info: {e}")
        await update.message.reply_text("❌ Произошла ошибка при удалении информации.")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик получения документов (только для владельца)."""
    try:
        user_id = update.effective_user.id
        
        # ВАЖНО: проверяем ТОЛЬКО если это владелец (6893832048)
        if not is_owner(user_id):
            # Игнорируем документы от всех остальных пользователей
            return
        
        document = update.message.document
        
        # Проверяем, что это файл базы данных
        if document.file_name != "info.db":
            await update.message.reply_text("❌ Пожалуйста, отправьте файл с именем 'info.db'")
            return
        
        file = await document.get_file()
        temp_path = f"temp_{document.file_name}"
        await file.download_to_drive(temp_path)
        
        progress_msg = await update.message.reply_text("🔄 Начинаю импорт базы данных...")
        
        try:
            imported_count = import_database_from_file(temp_path)
            os.remove(temp_path)
            
            await progress_msg.edit_text(
                f"✅ База данных успешно импортирована!\n"
                f"• Загружено записей: {imported_count}\n"
                f"• Создана резервная копия предыдущей версии"
            )
            
        except Exception as e:
            await progress_msg.edit_text(f"❌ Ошибка при импорте: {str(e)[:200]}")
            logger.error(f"Ошибка импорта: {e}")
            
            if os.path.exists(temp_path):
                os.remove(temp_path)
                
    except Exception as e:
        logger.error(f"Ошибка в handle_document: {e}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает текстовые сообщения."""
    try:
        if not update.message or not update.message.text:
            return
        
        text = update.message.text
        
        if text.startswith('!инфо '):
            await handle_info_command(update, context)
        elif text.startswith('+инфо '):
            await handle_add_info(update, context)
        elif text.startswith('-инфо '):
            await handle_delete_info(update, context)
            
    except Exception as e:
        logger.error(f"Ошибка в handle_message: {e}")

# ========== ОСНОВНАЯ ФУНКЦИЯ ==========
def main():
    """Основная функция запуска бота."""
    # Инициализация базы данных
    init_db()
    
    # Очистка старых записей при запуске
    cleaned_count = cleanup_database()
    cleanup_old_backups()
    
    # Загружаем администраторов
    logger.info(f"Загружены администраторы: {ADMIN_IDS}")
    
    # Создаем приложение
    application = Application.builder().token(TOKEN).build()
    
    # Добавляем обработчики команд
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("tops", tops_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("backup", backup_command))
    application.add_handler(CommandHandler("cleanup", cleanup_command))
    
    # Добавляем обработчики сообщений
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # ВАЖНО: обработчик документов ТОЛЬКО для владельца
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    # Планировщик для автоматической очистки
    scheduler = BackgroundScheduler()
    scheduler.add_job(cleanup_database, 'interval', days=1)
    scheduler.add_job(cleanup_old_backups, 'interval', days=1)
    scheduler.start()
    
    # Запуск бота
    print("=" * 50)
    print("🤖 Бот запущен...")
    print("=" * 50)
    print(f" Главный владелец: {ADMIN_IDS[0]}")
    print(f"🧹 Очищено записей в БД: {cleaned_count}")
    print()
    print("📋 Основные команды:")
    print("/help - Справка по командам")
    print("/tops - Весь список информации (доступно всем)")
    print("+инфо @ник текст - добавить информацию")
    print("-инфо @ник - удалить информацию")
    print("!инфо @ник - узнать информацию")
    print()
    print("🛠️ Для импорта БД: отправьте файл info.db в чат с ботом")
    print("   (только для владельца бота)")
    print("📝 Логи сохраняются в файл bot.log")
    print("=" * 50)
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()

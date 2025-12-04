import logging
import sqlite3
import re
import json
import csv
import os
from io import BytesIO, StringIO
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    CommandHandler,
    filters,
)

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO,
    filename='bot.log'  # Добавляем запись логов в файл
)
logger = logging.getLogger(__name__)

# Токен бота (замените на свой)
BOT_TOKEN = "8534057742:AAFfm2gswdz-b6STcrWcCdRfaToRDkPUu0A"
# ID администраторов (список Telegram ID)
ADMIN_IDS = [6893832048, 8000395560]  # Ваши Telegram ID

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

# Получение информации о конкретном пользователе
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

# Проверка админских прав в группе
async def is_admin(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> bool:
    try:
        admins = await context.bot.get_chat_administrators(chat_id)
        admin_ids = [admin.user.id for admin in admins]
        return user_id in admin_ids
    except Exception as e:
        logger.error(f"Ошибка при проверке прав администратора: {e}")
        # Если не удалось получить список админов, разрешаем доступ только владельцам бота
        return user_id in ADMIN_IDS

# Проверка что пользователь - владелец бота (в списке ADMIN_IDS)
def is_bot_owner(user_id: int) -> bool:
    return user_id in ADMIN_IDS

# Обработчик команды /export_db
async def export_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        
        # Проверяем, что команду вызвал владелец бота
        if not is_bot_owner(user_id):
            await update.message.reply_text("❌ Эта команда доступна только владельцу бота!")
            return
            
        # Проверяем существование базы данных
        if not os.path.exists("info.db"):
            await update.message.reply_text("❌ База данных не найдена!")
            return
            
        # Отправляем файл базы данных
        with open("info.db", "rb") as db_file:
            await update.message.reply_document(
                document=db_file,
                filename="info.db",
                caption="📦 База данных бота"
            )
        logger.info(f"База данных экспортирована пользователем {user_id}")
        
    except Exception as e:
        logger.error(f"Ошибка при экспорте базы данных: {e}")
        await update.message.reply_text("❌ Произошла ошибка при экспорте базы данных!")

# Обработчик команды /export_logs
async def export_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        
        # Проверяем, что команду вызвал владелец бота
        if not is_bot_owner(user_id):
            await update.message.reply_text("❌ Эта команда доступна только владельцу бота!")
            return
            
        # Проверяем существование файла логов
        if not os.path.exists("bot.log"):
            await update.message.reply_text("❌ Файл логов не найден!")
            return
            
        # Отправляем файл логов
        with open("bot.log", "rb") as log_file:
            await update.message.reply_document(
                document=log_file,
                filename="bot.log",
                caption="📋 Логи бота"
            )
        logger.info(f"Логи экспортированы пользователем {user_id}")
        
    except Exception as e:
        logger.error(f"Ошибка при экспорте логов: {e}")
        await update.message.reply_text("❌ Произошла ошибка при экспорте логов!")

# Обработчик команды /import_db
async def import_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = update.effective_user.id
        
        # Проверяем, что команду вызвал владелец бота
        if not is_bot_owner(user_id):
            await update.message.reply_text("❌ Эта команда доступна только владельцу бота!")
            return
        
        # Проверяем, что сообщение содержит документ
        if not update.message.document:
            await update.message.reply_text(
                "📁 Для импорта базы данных отправьте файл info.db в ответ на это сообщение\n\n"
                "⚠️ **Внимание:** Существующая база данных будет перезаписана!"
            )
            return
        
        # Проверяем имя файла
        document = update.message.document
        if document.file_name != "info.db":
            await update.message.reply_text("❌ Неверный файл. Ожидается файл с именем 'info.db'")
            return
        
        # Скачиваем файл
        file = await context.bot.get_file(document.file_id)
        
        # Создаем резервную копию текущей базы данных
        if os.path.exists("info.db"):
            backup_name = f"info.db.backup_{int(time.time())}"
            os.rename("info.db", backup_name)
            logger.info(f"Создана резервная копия базы данных: {backup_name}")
        
        # Сохраняем новую базу данных
        await file.download_to_drive("info.db")
        
        # Проверяем валидность базы данных
        try:
            conn = sqlite3.connect("info.db")
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM user_info")
            count = cursor.fetchone()[0]
            conn.close()
            
            await update.message.reply_text(
                f"✅ База данных успешно импортирована!\n"
                f"📊 Записей в базе: {count}\n\n"
                f"🔄 Бот будет перезагружен для применения изменений..."
            )
            
            # Перезапускаем бота
            os._exit(0)
            
        except sqlite3.Error as e:
            # Восстанавливаем резервную копию при ошибке
            if os.path.exists(backup_name):
                os.remove("info.db")
                os.rename(backup_name, "info.db")
            
            await update.message.reply_text(f"❌ Ошибка в импортированной базе данных: {e}")
            logger.error(f"Ошибка при импорте базы данных: {e}")
            
    except Exception as e:
        logger.error(f"Ошибка при импорте базы данных: {e}")
        await update.message.reply_text("❌ Произошла ошибка при импорте базы данных!")

# Обработчик команды /help_admin
async def help_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_bot_owner(user_id):
        await update.message.reply_text("❌ Эта команда доступна только владельцу бота!")
        return
    
    help_text = """
🛠️ **Команды для администратора бота:**

/export_db - Экспортировать базу данных
/export_logs - Экспортировать логи бота
/import_db - Импортировать базу данных (отправьте файл info.db в ответ)
/help_admin - Показать это сообщение

📝 **Команды для админов группы:**
/tops - Показать весь список информации
+инфо @username текст - Добавить информацию
-инфо @username - Удалить информацию
!инфо @username - Узнать информацию

⚠️ **Важно:**
- При импорте базы данных старая будет заменена
- Рекомендуется сделать экспорт перед импортом
- Бот перезагружается после импорта базы данных
    """
    
    await update.message.reply_text(help_text, parse_mode="Markdown")

# Обработчик команды /admins
async def show_admins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_bot_owner(user_id):
        await update.message.reply_text("❌ Эта команда доступна только владельцу бота!")
        return
    
    admins_list = "\n".join([f"• {admin_id}" for admin_id in ADMIN_IDS])
    await update.message.reply_text(f"👑 Владельцы бота:\n{admins_list}")

# Обработчик команды /tops
async def tops(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        logger.info(f"Получена команда /tops от пользователя {update.effective_user.id}")
        
        # Проверяем, что команда пришла в групповом чате
        if update.effective_chat.type not in ['group', 'supergroup']:
            await update.message.reply_text("❌ Эта команда доступна только в группах!")
            return
            
        # Проверяем админские права (опционально, можно убрать если нужно всем)
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id
        
        if not await is_admin(context, chat_id, user_id):
            await update.message.reply_text("❌ Только администраторы могут использовать эту команду!")
            return
            
        rows = get_all_info()
        if not rows:
            await update.message.reply_text("📭 Список пуст.")
            return

        response = "📋 Список информации:\n\n"
        for username, first_name, last_name, user_id, text in rows:
            # Формируем отображаемое имя
            if username:
                display_name = f"@{username}"
            elif first_name and last_name:
                display_name = f"{first_name} {last_name}"
            elif first_name:
                display_name = first_name
            else:
                display_name = f"id{user_id}"
            
            # Формируем ссылку если есть user_id
            if user_id and user_id != 0:
                # Создаем Markdown ссылку на аккаунт
                user_link = f"[{display_name}](tg://user?id={user_id})"
            else:
                user_link = display_name
            
            # Заменяем 0 на ↔ в user_id при отображении
            user_id_display = "↔" if user_id == 0 else user_id
            
            response += f"{user_link} | {user_id_display} | {text}\n"

        # Если сообщение слишком длинное, разбиваем на части
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
                    # Для последующих сообщений добавляем заголовок
                    await update.message.reply_text(f"📋 Продолжение ({i+1}/{len(parts)}):\n\n{part}", 
                                                  parse_mode="Markdown", 
                                                  disable_web_page_preview=True)
        else:
            await update.message.reply_text(response, parse_mode="Markdown", disable_web_page_preview=True)
            
    except Exception as e:
        logger.error(f"Ошибка в команде /tops: {e}")
        await update.message.reply_text("❌ Произошла ошибка при выполнении команды. Проверьте логи бота.")

# Обработчик +инфо
async def add_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    message = update.message.text
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    # Проверяем админские права
    if not await is_admin(context, chat_id, user_id):
        await update.message.reply_text("❌ Только админы могут использовать эту команду!")
        return

    # Парсинг: +инфо @username текст
    match = re.match(r"^\+\s*инфо\s+(@?\w+)\s+(.+)$", message, re.DOTALL)
    if not match:
        await update.message.reply_text("📝 Используйте формат: `+инфо @username текст`", parse_mode="Markdown")
        return

    target = match.group(1).lower()  # Может быть @username или просто текст
    info_text = match.group(2).strip()
    
    # Убираем @ если есть
    if target.startswith('@'):
        target = target[1:]
    
    target_user_id = 0
    first_name = ""
    last_name = ""
    actual_username = target

    # Пытаемся найти пользователя
    try:
        # Сначала пытаемся как username
        try:
            chat_member = await context.bot.get_chat_member(chat_id, f"@{target}")
            target_user_id = chat_member.user.id
            actual_username = chat_member.user.username or target
            first_name = chat_member.user.first_name or ""
            last_name = chat_member.user.last_name or ""
        except:
            # Пробуем поискать по ID (если target - число)
            if target.isdigit():
                chat_member = await context.bot.get_chat_member(chat_id, int(target))
                target_user_id = chat_member.user.id
                actual_username = chat_member.user.username or f"id{target}"
                first_name = chat_member.user.first_name or ""
                last_name = chat_member.user.last_name or ""
    except Exception as e:
        logging.warning(f"Не удалось получить информацию для {target}: {e}")
        # Сохраняем как есть

    # Проверяем, есть ли уже информация о пользователе
    existing_info = get_user_info_by_username(actual_username)
    if not existing_info and target_user_id != 0:
        existing_info = get_user_info_by_id(target_user_id)
    
    if existing_info:
        await update.message.reply_text(f"ℹ️ Информация о @{actual_username} уже есть. Используйте `-инфо @{actual_username}` чтобы удалить.")
        return

    # Сохраняем
    save_info(actual_username, first_name, last_name, target_user_id, info_text)
    await update.message.reply_text(f"✅ Информация для @{actual_username} сохранена: {info_text}")

# Обработчик -инфо
async def remove_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    message = update.message.text
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    # Проверяем админские права
    if not await is_admin(context, chat_id, user_id):
        await update.message.reply_text("❌ Только админы могут использовать эту команду!")
        return

    # Парсинг: -инфо @username
    match = re.match(r"^-\s*инфо\s+@?(\w+)$", message)
    if not match:
        await update.message.reply_text("📝 Используйте формат: `-инфо @username`", parse_mode="Markdown")
        return

    target_username = match.group(1).lower()

    # Проверяем, есть ли информация о пользователе
    existing_info = get_user_info_by_username(target_username)
    if not existing_info:
        await update.message.reply_text(f"ℹ️ Информации о @{target_username} не найдено.")
        return

    # Удаляем информацию
    deleted_count = delete_user_info(target_username)
    if deleted_count > 0:
        await update.message.reply_text(f"🗑️ Информация о @{target_username} удалена.")
    else:
        await update.message.reply_text(f"⚠️ Не удалось удалить информацию о @{target_username}.")

# Обработчик !инфо
async def get_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    message = update.message.text
    
    # Парсинг: !инфо @username
    match = re.match(r"^!\s*инфо\s+@?(\w+)$", message)
    if not match:
        await update.message.reply_text("📝 Используйте формат: `!инфо @username`", parse_mode="Markdown")
        return

    target_username = match.group(1).lower()

    # Получаем информацию о пользователе
    user_info = get_user_info_by_username(target_username)
    
    if not user_info:
        await update.message.reply_text(f"❌ Информации о @{target_username} не найдено.")
        return

    username, first_name, last_name, user_id, text = user_info
    
    # Формируем отображаемое имя
    if username:
        display_name = f"@{username}"
    elif first_name and last_name:
        display_name = f"{first_name} {last_name}"
    elif first_name:
        display_name = first_name
    else:
        display_name = f"id{user_id}"
    
    # Формируем ссылку если есть user_id
    if user_id and user_id != 0:
        user_link = f"[{display_name}](tg://user?id={user_id})"
    else:
        user_link = display_name
    
    # Заменяем 0 на ↔ в user_id при отображении
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

# Обработчик для всех сообщений (для отладки)
async def debug_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Получено сообщение: {update.message.text} от {update.effective_user.id}")

# Запуск
if __name__ == "__main__":
    import time
    
    # Инициализация базы данных
    init_db()
    
    # Создание приложения
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Регистрируем обработчики команд для владельца бота
    app.add_handler(CommandHandler("export_db", export_db))
    app.add_handler(CommandHandler("export_logs", export_logs))
    app.add_handler(CommandHandler("import_db", import_db))
    app.add_handler(CommandHandler("help_admin", help_admin))
    app.add_handler(CommandHandler("admins", show_admins))
    
    # Регистрируем обработчики команд для всех пользователей
    app.add_handler(CommandHandler("tops", tops))
    
    # Регистрируем обработчик сообщений
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Добавляем обработчик для отладки (можно убрать после тестирования)
    app.add_handler(MessageHandler(filters.ALL, debug_handler))

    print("=" * 50)
    print("🤖 Бот запущен...")
    print("=" * 50)
    print(f"\n👑 Владельцы бота: {ADMIN_IDS}")
    print("\n👑 Команды для владельцев бота:")
    print("/export_db - Экспортировать базу данных")
    print("/export_logs - Экспортировать логи бота")
    print("/import_db - Импортировать базу данных (отправьте файл info.db)")
    print("/help_admin - Справка по командам администратора")
    print("/admins - Показать список владельцев бота")
    print("\n👥 Команды для админов группы:")
    print("/tops - Показать весь список информации")
    print("+инфо @ник текст - добавить информацию")
    print("-инфо @ник - удалить информацию")
    print("!инфо @ник - узнать информацию")
    print("\n📝 Логи сохраняются в файл bot.log")
    print("=" * 50)
    
    app.run_polling()

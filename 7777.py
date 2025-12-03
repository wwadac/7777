import logging
import sqlite3
import re
import json
import csv
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
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

# Токен бота (замените на свой)
BOT_TOKEN = "8534057742:AAFfm2gswdz-b6STcrWcCdRfaToRDkPUu0A"
# ID администратора (замените на свой Telegram ID)
ADMIN_ID = 6893832048  # Ваш Telegram ID

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect("info.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_info (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            user_id INTEGER,
            text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

# Сохранение данных
def save_info(username: str, user_id: int, text: str):
    conn = sqlite3.connect("info.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO user_info (username, user_id, text) VALUES (?, ?, ?)", 
                   (username, user_id, text))
    conn.commit()
    conn.close()

# Получение всех записей
def get_all_info():
    conn = sqlite3.connect("info.db")
    cursor = conn.cursor()
    cursor.execute("SELECT username, user_id, text FROM user_info ORDER BY username")
    rows = cursor.fetchall()
    conn.close()
    return rows

# Получение информации о конкретном пользователе
def get_user_info(username: str):
    conn = sqlite3.connect("info.db")
    cursor = conn.cursor()
    cursor.execute("SELECT username, user_id, text FROM user_info WHERE username = ?", (username,))
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

# Получение базы данных как файл
def get_db_file():
    with open("info.db", "rb") as f:
        return BytesIO(f.read())

# Экспорт данных в JSON
def export_to_json():
    conn = sqlite3.connect("info.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM user_info")
    rows = cursor.fetchall()
    
    # Получаем названия колонок
    cursor.execute("PRAGMA table_info(user_info)")
    columns = [column[1] for column in cursor.fetchall()]
    
    # Конвертируем в список словарей
    data = []
    for row in rows:
        data.append(dict(zip(columns, row)))
    
    conn.close()
    
    # Создаем JSON строку
    json_str = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    return StringIO(json_str)

# Экспорт данных в CSV
def export_to_csv():
    conn = sqlite3.connect("info.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM user_info")
    rows = cursor.fetchall()
    
    # Получаем названия колонок
    cursor.execute("PRAGMA table_info(user_info)")
    columns = [column[1] for column in cursor.fetchall()]
    
    conn.close()
    
    # Создаем CSV в памяти
    output = StringIO()
    writer = csv.writer(output)
    
    # Записываем заголовки
    writer.writerow(columns)
    
    # Записываем данные
    for row in rows:
        writer.writerow(row)
    
    output.seek(0)
    return StringIO(output.getvalue())

# Проверка админских прав
async def is_admin(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> bool:
    admins = await context.bot.get_chat_administrators(chat_id)
    admin_ids = [admin.user.id for admin in admins]
    return user_id in admin_ids

# Проверка прав глобального админа
def is_global_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID

# Обработчик команды /tops
async def tops(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = get_all_info()
    if not rows:
        await update.message.reply_text("📭 Список пуст.")
        return

    response = "📋 Список информации:\n\n"
    for username, user_id, text in rows:
        # Заменяем 0 на ↔ в user_id при отображении
        user_id_display = "↔" if user_id == 0 else user_id
        username_display = f"@{username}" if username else f"id{user_id}"
        response += f"{username_display} | {user_id_display} | {text}\n"

    # Если сообщение слишком длинное, разбиваем на части
    if len(response) > 4096:
        for i in range(0, len(response), 4096):
            await update.message.reply_text(response[i:i+4096])
    else:
        await update.message.reply_text(response)

# Обработчик команды /export
async def export_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Проверяем права глобального админа
    if not is_global_admin(user_id):
        await update.message.reply_text("❌ Эта команда только для глобального администратора!")
        return
    
    if not context.args:
        await update.message.reply_text(
            "📤 Используйте:\n"
            "`/export json` - экспорт в JSON\n"
            "`/export csv` - экспорт в CSV\n"
            "`/export db` - скачать базу данных",
            parse_mode="Markdown"
        )
        return
    
    export_type = context.args[0].lower()
    
    try:
        if export_type == "json":
            json_file = export_to_json()
            await update.message.reply_document(
                document=BytesIO(json_file.getvalue().encode('utf-8')),
                filename="user_info.json",
                caption="📄 Экспорт данных в JSON"
            )
            
        elif export_type == "csv":
            csv_file = export_to_csv()
            await update.message.reply_document(
                document=BytesIO(csv_file.getvalue().encode('utf-8')),
                filename="user_info.csv",
                caption="📊 Экспорт данных в CSV"
            )
            
        elif export_type == "db":
            db_file = get_db_file()
            await update.message.reply_document(
                document=db_file,
                filename="info.db",
                caption="💾 Полная база данных SQLite"
            )
            
        else:
            await update.message.reply_text("❌ Неверный формат. Используйте: json, csv или db")
            
    except Exception as e:
        logging.error(f"Ошибка при экспорте: {e}")
        await update.message.reply_text(f"❌ Ошибка при экспорте: {str(e)}")

# Обработчик команды /stats
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Проверяем права глобального админа
    if not is_global_admin(user_id):
        await update.message.reply_text("❌ Эта команда только для глобального администратора!")
        return
    
    conn = sqlite3.connect("info.db")
    cursor = conn.cursor()
    
    # Получаем статистику
    cursor.execute("SELECT COUNT(*) FROM user_info")
    total_records = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(DISTINCT username) FROM user_info")
    unique_users = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM user_info WHERE user_id = 0")
    unknown_id = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM user_info WHERE user_id != 0")
    known_id = cursor.fetchone()[0]
    
    cursor.execute("SELECT created_at FROM user_info ORDER BY id DESC LIMIT 1")
    last_record = cursor.fetchone()
    last_update = last_record[0] if last_record else "нет данных"
    
    conn.close()
    
    stats_text = (
        "📊 Статистика базы данных:\n\n"
        f"📝 Всего записей: {total_records}\n"
        f"👤 Уникальных пользователей: {unique_users}\n"
        f"🔍 С известным ID: {known_id}\n"
        f"❓ С неизвестным ID: {unknown_id}\n"
        f"🕐 Последнее обновление: {last_update}\n\n"
        f"🆔 Ваш ID: {user_id}"
    )
    
    await update.message.reply_text(stats_text)

# Обработчик команды /backup
async def backup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Проверяем права глобального админа
    if not is_global_admin(user_id):
        await update.message.reply_text("❌ Эта команда только для глобального администратора!")
        return
    
    try:
        db_file = get_db_file()
        await update.message.reply_document(
            document=db_file,
            filename=f"backup_info_{update.message.date.strftime('%Y%m%d_%H%M%S')}.db",
            caption="💾 Автоматический бэкап базы данных"
        )
    except Exception as e:
        logging.error(f"Ошибка при создании бэкапа: {e}")
        await update.message.reply_text(f"❌ Ошибка при создании бэкапа: {str(e)}")

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
    match = re.match(r"^\+\s*инфо\s+@?(\w+)\s+(.+)$", message, re.DOTALL)
    if not match:
        await update.message.reply_text("📝 Используйте формат: `+инфо @username текст`", parse_mode="Markdown")
        return

    target_username = match.group(1).lower()
    info_text = match.group(2).strip()

    # Проверяем, есть ли уже информация о пользователе
    existing_info = get_user_info(target_username)
    if existing_info:
        await update.message.reply_text(f"ℹ️ Информация о @{target_username} уже есть. Используйте `-инфо @{target_username}` чтобы удалить.")
        return

    # Пытаемся получить user_id
    target_user_id = 0
    try:
        chat_member = await context.bot.get_chat_member(chat_id, f"@{target_username}")
        target_user_id = chat_member.user.id
        actual_username = chat_member.user.username or target_username
    except Exception as e:
        actual_username = target_username
        logging.warning(f"Не удалось получить ID для @{target_username}: {e}")

    # Сохраняем
    save_info(actual_username, target_user_id, info_text)
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
    existing_info = get_user_info(target_username)
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
    user_info = get_user_info(target_username)
    
    if not user_info:
        await update.message.reply_text(f"❌ Информации о @{target_username} не найдено.")
        return

    username, user_id, text = user_info
    username_display = f"@{username}" if username else f"id{user_id}"
    
    # Заменяем 0 на ↔ в user_id при отображении
    user_id_display = "↔" if user_id == 0 else user_id
    response = f"👤 {username_display} | {user_id_display} | {text}"
    await update.message.reply_text(response)

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

# Запуск
if __name__ == "__main__":
    # Инициализация базы данных
    init_db()
    
    # Создание приложения
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Регистрируем обработчики команд
    app.add_handler(CommandHandler("tops", tops))
    app.add_handler(CommandHandler("export", export_data))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("backup", backup))
    
    # Регистрируем обработчик сообщений
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Бот запущен...")
    print(f"ID администратора: {ADMIN_ID}")
    print("Команды администратора:")
    print("/export <json|csv|db> - скачать данные")
    print("/stats - статистика базы")
    print("/backup - бэкап базы данных")
    
    app.run_polling()

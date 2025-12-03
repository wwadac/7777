import logging
import sqlite3
import re
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

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect("info.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_info (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            user_id INTEGER,
            text TEXT
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

# Проверка админских прав
async def is_admin(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> bool:
    admins = await context.bot.get_chat_administrators(chat_id)
    admin_ids = [admin.user.id for admin in admins]
    return user_id in admin_ids

# Обработчик команды /tops
async def tops(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = get_all_info()
    if not rows:
        await update.message.reply_text("📭 Список пуст.")
        return

    response = "📋 Список информации:\n\n"
    for username, user_id, text in rows:
        username_display = f"@{username}" if username else f"id{user_id}"
        response += f"{username_display} | {user_id} | {text}\n"

    # Если сообщение слишком длинное, разбиваем на части
    if len(response) > 4096:
        for i in range(0, len(response), 4096):
            await update.message.reply_text(response[i:i+4096])
    else:
        await update.message.reply_text(response)

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

    target_username = match.group(1).lower()  # username в нижний регистр для единообразия
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
    
    response = f"👤 {username_display} | {user_id} | {text}"
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
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Регистрируем обработчики
    app.add_handler(CommandHandler("tops", tops))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Бот запущен...")
    app.run_polling()

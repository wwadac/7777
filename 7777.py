import os
import logging
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Получаем токен бота из переменных окружения
BOT_TOKEN = os.getenv('7977469319:AAGWsXON1zGZnXUo8kmnM_ehRBbRekfsNTU')

async def delete_slot_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Удаляет сообщения со слотами, если есть хотя бы одна семерка"""
    try:
        message = update.message
        
        # Проверяем, есть ли в сообщении эмодзи слотов 🎰
        if '🎰' in message.text:
            # Проверяем, есть ли в сообщении хотя бы одна цифра 7
            if '7' in message.text:
                # Удаляем сообщение
                await message.delete()
                logging.info(f"Сообщение удалено: {message.text}")
                
                # Отправляем подтверждение удаления (опционально)
                notification = await message.reply_text("🎰 Найдена семерка! Сообщение удалено.")
                
                # Удаляем само уведомление через 5 секунд
                await context.job_queue.run_once(
                    delete_notification, 
                    5, 
                    data=notification.chat_id, 
                    name=str(notification.message_id)
                )
                
    except Exception as e:
        logging.error(f"Ошибка при обработке сообщения: {e}")

async def delete_notification(context: ContextTypes.DEFAULT_TYPE):
    """Удаляет уведомление об удалении"""
    job = context.job
    try:
        await context.bot.delete_message(job.data, int(job.name))
    except Exception as e:
        logging.error(f"Ошибка при удалении уведомления: {e}")

def main():
    """Запуск бота"""
    if not BOT_TOKEN:
        print("Ошибка: BOT_TOKEN не установлен!")
        return
    
    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Добавляем обработчик сообщений со слотами
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, delete_slot_messages))
    
    # Запускаем бота
    print("Бот запущен...")
    application.run_polling()

if __name__ == '__main__':
    main()
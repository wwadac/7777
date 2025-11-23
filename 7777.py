import requests
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import logging

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Твой токен бота (получи у @BotFather)
BOT_TOKEN = "8324933170:AAFatQ1T42ZJ70oeWS2UJkcXFeiwUFCIXAk"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    await update.message.reply_text(
        "Привет! Я бот для отслеживания онлайна на сервере.\n"
        "Используй /online чтобы узнать текущий онлайн"
    )

async def get_online(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Парсит и возвращает онлайн с сайта"""
    try:
        url = "https://phoenix.easydonate.ru/"
        
        # Создаем заголовки чтобы избежать блокировки
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        # Получаем HTML страницу[citation:7]
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()  # Проверяем успешность запроса
        
        # Парсим HTML[citation:2]
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Ищем информацию об онлайне (тебе нужно уточнить селекторы)
        # Вот несколько возможных вариантов поиска:
        
        # Вариант 1: Поиск по тексту
        online_text = None
        for element in soup.find_all(text=True):
            if 'онлайн' in element.lower() or 'online' in element.lower():
                online_text = element.strip()
                break
        
        # Вариант 2: Поиск по классам или ID (нужно уточнить через Инспектор)
        # online_element = soup.find('div', class_='online-class') 
        # или
        # online_element = soup.find('span', id='online-count')
        
        if online_text:
            await update.message.reply_text(f"📊 Текущий онлайн: {online_text}")
        else:
            # Если не нашли онлайн, покажем всю страницу для отладки
            await update.message.reply_text(
                "Не удалось найти информацию об онлайне.\n"
                "Вот содержимое страницы для отладки:\n"
                f"{soup.get_text()[:1000]}..."  # Первые 1000 символов
            )
            
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка при получении данных: {str(e)}")

def main():
    """Основная функция"""
    # Создаем приложение[citation:7]
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Добавляем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("online", get_online))
    
    # Запускаем бота
    print("Бот запущен...")
    application.run_polling()

if __name__ == '__main__':
    main()

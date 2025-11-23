import logging
import requests
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Токен бота (получите у @BotFather)
BOT_TOKEN = "8324933170:AAFatQ1T42ZJ70oeWS2UJkcXFeiwUFCIXAk"

# Функция для парсинга данных
def parse_website(url):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Пример парсинга - измените под ваш сайт
        data = {
            'title': soup.title.string if soup.title else 'No title',
            'headers': [],
            'links': []
        }
        
        # Парсим заголовки h1-h3
        for i in range(1, 4):
            headers = soup.find_all(f'h{i}')
            for header in headers[:5]:  # Берем первые 5 заголовков
                data['headers'].append(header.get_text().strip())
        
        # Парсим ссылки
        links = soup.find_all('a', href=True)
        for link in links[:10]:  # Берем первые 10 ссылок
            data['links'].append({
                'text': link.get_text().strip()[:50],  # Обрезаем длинный текст
                'url': link['href']
            })
        
        return data
        
    except Exception as e:
        return {'error': str(e)}

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я бот для парсинга сайтов.\n"
        "Отправь мне URL сайта, и я покажу его содержимое.\n\n"
        "Пример: https://example.com"
    )

# Обработка текстовых сообщений с URL
async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    
    # Проверяем, что это валидный URL
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    await update.message.reply_text(f"🔄 Парсим сайт: {url}")
    
    # Парсим данные
    data = parse_website(url)
    
    if 'error' in data:
        await update.message.reply_text(f"❌ Ошибка: {data['error']}")
        return
    
    # Формируем ответ
    response_text = f"📄 **Результаты парсинга:**\n\n"
    response_text += f"**Заголовок страницы:** {data['title']}\n\n"
    
    if data['headers']:
        response_text += "**Основные заголовки:**\n"
        for header in data['headers']:
            response_text += f"• {header}\n"
        response_text += "\n"
    
    if data['links']:
        response_text += "**Ссылки:**\n"
        for link in data['links']:
            response_text += f"• {link['text']} - {link['url']}\n"
    
    # Отправляем результат (разбиваем на части если слишком длинный)
    if len(response_text) > 4096:
        for x in range(0, len(response_text), 4096):
            await update.message.reply_text(response_text[x:x+4096])
    else:
        await update.message.reply_text(response_text)

# Обработка ошибок
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.error(f"Ошибка: {context.error}")

# Главная функция
def main():
    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    application.add_error_handler(error_handler)
    
    # Запускаем бота
    print("Бот запущен...")
    application.run_polling()

if __name__ == '__main__':
    main()

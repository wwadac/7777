import os
import logging
from pathlib import Path
import asyncio
from datetime import datetime

from aiogram import Bot, Dispatcher, types
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.utils.markdown import hbold
from dotenv import load_dotenv
import ffmpeg
import speech_recognition as sr
from pydub import AudioSegment
import subprocess

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Токен бота
BOT_TOKEN = os.getenv('BOT_TOKEN')

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Создание директорий для временных файлов
TEMP_DIR = Path("temp")
TEMP_DIR.mkdir(exist_ok=True)
VIDEO_DIR = TEMP_DIR / "videos"
AUDIO_DIR = TEMP_DIR / "audio"
VIDEO_DIR.mkdir(exist_ok=True)
AUDIO_DIR.mkdir(exist_ok=True)

# Максимальный размер файла (20 MB)
MAX_FILE_SIZE = 20 * 1024 * 1024

@dp.message(Command("start"))
async def start_command(message: Message):
    """Обработчик команды /start"""
    welcome_text = (
        f"Привет, {hbold(message.from_user.full_name)}! 👋\n\n"
        "Я бот с двумя функциями:\n\n"
        "1️⃣ 📹 Конвертирую видео в кружок (видеосообщение)\n"
        "   - Просто отправь мне видео\n"
        "   - Видео должно быть не больше 20 МБ\n"
        "   - Я обрежу его до квадрата и сделаю кружок\n\n"
        "2️⃣ 🎤 Превращаю голосовые сообщения в текст\n"
        "   - Отправь мне голосовое сообщение\n"
        "   - Поддерживаются разные языки\n"
        "   - Я распознаю речь и отправлю текст\n\n"
        "Просто отправь видео или голосовое сообщение!"
    )
    await message.answer(welcome_text, parse_mode="HTML")

@dp.message(Command("help"))
async def help_command(message: Message):
    """Обработчик команды /help"""
    help_text = (
        "📋 Инструкция по использованию:\n\n"
        "🎬 Для видео:\n"
        "1. Отправь видео файл (до 20 МБ)\n"
        "2. Я обработаю его и сделаю кружок\n"
        "3. Отправлю тебе видеосообщение\n\n"
        "🎤 Для голосовых:\n"
        "1. Отправь голосовое сообщение\n"
        "2. Я распознаю речь\n"
        "3. Отправлю тебе текст\n\n"
        "Команды:\n"
        "/start - Начать работу\n"
        "/help - Показать помощь"
    )
    await message.answer(help_text)

async def convert_to_circle(input_path: Path, output_path: Path) -> bool:
    """
    Конвертирует обычное видео в кружок (квадратное видео с круглой маской)
    """
    try:
        # Получаем информацию о видео
        probe = ffmpeg.probe(str(input_path))
        video_stream = next((stream for stream in probe['streams'] if stream['codec_type'] == 'video'), None)
        
        if video_stream is None:
            return False
        
        width = int(video_stream['width'])
        height = int(video_stream['height'])
        
        # Определяем размер для квадрата (минимальная сторона)
        size = min(width, height)
        
        # Координаты для обрезки
        x = (width - size) // 2
        y = (height - size) // 2
        
        # Создаем сложный фильтр для создания кружка
        # 1. Обрезаем до квадрата
        # 2. Создаем круглую маску
        # 3. Применяем маску к видео
        filter_complex = (
            f"[0:v]crop={size}:{size}:{x}:{y}[cropped];"
            f"[cropped]format=rgba,geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='if(gt(pow(X-({size}/2),2)+pow(Y-({size}/2),2),pow({size}/2,2)),0,255)'[circlevideo]"
        )
        
        # Применяем фильтр
        process = (
            ffmpeg
            .input(str(input_path))
            .output(
                str(output_path),
                vcodec='libx264',
                acodec='aac',
                video_bitrate='1000k',
                audio_bitrate='128k',
                **{'filter_complex': filter_complex, 'map': '[circlevideo]'}
            )
            .overwrite_output()
            .run_async(pipe_stdout=True, pipe_stderr=True)
        )
        
        # Ждем завершения
        stdout, stderr = process.communicate()
        
        if process.returncode != 0:
            logger.error(f"FFmpeg error: {stderr.decode()}")
            return False
            
        return True
        
    except Exception as e:
        logger.error(f"Error converting video: {e}")
        return False

async def speech_to_text(audio_path: Path) -> str:
    """
    Преобразует аудио в текст
    """
    try:
        # Инициализируем распознаватель
        recognizer = sr.Recognizer()
        
        # Конвертируем аудио в WAV формат для лучшего распознавания
        wav_path = audio_path.with_suffix('.wav')
        
        # Используем ffmpeg для конвертации
        stream = ffmpeg.input(str(audio_path))
        stream = ffmpeg.output(stream, str(wav_path), acodec='pcm_s16le', ac=1, ar='16000')
        ffmpeg.run(stream, overwrite_output=True, capture_stdout=True, capture_stderr=True)
        
        # Загружаем аудио для распознавания
        with sr.AudioFile(str(wav_path)) as source:
            audio_data = recognizer.record(source)
            
            # Пытаемся распознать на разных языках
            languages = ['ru-RU', 'uk-UA', 'en-US', 'de-DE', 'fr-FR']
            text = None
            
            for lang in languages:
                try:
                    text = recognizer.recognize_google(audio_data, language=lang)
                    logger.info(f"Recognized with language {lang}: {text}")
                    break
                except sr.UnknownValueError:
                    continue
                except sr.RequestError as e:
                    logger.error(f"Recognition service error: {e}")
                    continue
            
            if text:
                return text
            else:
                return "Не удалось распознать речь. Попробуйте говорить четче или на другом языке."
                
    except Exception as e:
        logger.error(f"Error in speech recognition: {e}")
        return f"Ошибка при распознавании: {str(e)}"
    finally:
        # Удаляем временный WAV файл
        if 'wav_path' in locals() and wav_path.exists():
            wav_path.unlink()

def cleanup_temp_files(*paths):
    """Удаляет временные файлы"""
    for path in paths:
        try:
            if path and Path(path).exists():
                Path(path).unlink()
        except Exception as e:
            logger.error(f"Error deleting file {path}: {e}")

@dp.message(lambda message: message.video or message.document)
async def handle_video(message: Message):
    """
    Обработчик видеофайлов
    """
    try:
        # Определяем тип файла и получаем информацию
        if message.video:
            file_info = message.video
            file_name = f"video_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
        else:
            # Проверяем, что это видео файл
            if not message.document.mime_type or not message.document.mime_type.startswith('video/'):
                await message.reply("Пожалуйста, отправьте видеофайл.")
                return
            file_info = message.document
            file_name = message.document.file_name or f"video_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
        
        # Проверяем размер файла
        if file_info.file_size > MAX_FILE_SIZE:
            await message.reply("❌ Файл слишком большой. Максимальный размер: 20 МБ")
            return
        
        # Отправляем сообщение о начале обработки
        processing_msg = await message.reply("🔄 Обрабатываю видео... Это может занять некоторое время.")
        
        # Скачиваем видео
        file_id = file_info.file_id
        file = await bot.get_file(file_id)
        
        input_path = VIDEO_DIR / f"input_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
        await bot.download_file(file.file_path, destination=input_path)
        
        # Конвертируем в кружок
        output_path = VIDEO_DIR / f"circle_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
        
        success = await convert_to_circle(input_path, output_path)
        
        if success and output_path.exists():
            # Отправляем видеосообщение
            with open(output_path, 'rb') as video_file:
                await message.reply_video_note(
                    video_note=types.BufferedInputFile(
                        video_file.read(),
                        filename="circle.mp4"
                    )
                )
            
            await processing_msg.edit_text("✅ Готово! Видео преобразовано в кружок.")
        else:
            await processing_msg.edit_text("❌ Не удалось обработать видео. Возможно, файл поврежден.")
        
        # Удаляем временные файлы
        cleanup_temp_files(input_path, output_path)
        
    except Exception as e:
        logger.error(f"Error handling video: {e}")
        await message.reply(f"❌ Произошла ошибка: {str(e)}")

@dp.message(lambda message: message.voice)
async def handle_voice(message: Message):
    """
    Обработчик голосовых сообщений
    """
    try:
        voice = message.voice
        
        # Проверяем размер (голосовые обычно маленькие)
        if voice.file_size > MAX_FILE_SIZE:
            await message.reply("❌ Голосовое сообщение слишком большое.")
            return
        
        # Отправляем сообщение о начале обработки
        processing_msg = await message.reply("🔄 Распознаю голосовое сообщение...")
        
        # Скачиваем голосовое сообщение
        file_id = voice.file_id
        file = await bot.get_file(file_id)
        
        # Определяем расширение (Telegram использует .oga)
        input_path = AUDIO_DIR / f"voice_{datetime.now().strftime('%Y%m%d_%H%M%S')}.oga"
        await bot.download_file(file.file_path, destination=input_path)
        
        # Распознаем речь
        text = await speech_to_text(input_path)
        
        # Отправляем результат
        await processing_msg.delete()
        
        response = f"📝 Распознанный текст:\n\n{text}"
        
        # Разбиваем длинные сообщения
        if len(response) > 4096:
            for x in range(0, len(response), 4096):
                await message.reply(response[x:x+4096])
        else:
            await message.reply(response)
        
        # Удаляем временный файл
        cleanup_temp_files(input_path)
        
    except Exception as e:
        logger.error(f"Error handling voice: {e}")
        await message.reply(f"❌ Произошла ошибка: {str(e)}")

@dp.message()
async def handle_unknown(message: Message):
    """Обработчик всех остальных сообщений"""
    await message.reply(
        "Я понимаю только видео и голосовые сообщения. "
        "Отправь видео для создания кружка или голосовое для распознавания текста.\n"
        "Используй /help для справки."
    )

async def main():
    """Главная функция запуска бота"""
    logger.info("Starting bot...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

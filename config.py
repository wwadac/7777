# ══════════════════════════════════════════════
# ⚙️ КОНФИГУРАЦИЯ БОТА — ЗАПОЛНИ СВОИ ДАННЫЕ
# ══════════════════════════════════════════════

# 🤖 Токен Telegram-бота (от @BotFather)
BOT_TOKEN = "8602705022:AAE7_Q9H42YfXE1aFF2kHuGV4-dnRXrk_Bo"

# 👑 ID администраторов (можно несколько через запятую)
ADMIN_IDS = [6893832048]

# 💳 Токен CryptoBot (от @CryptoBot → "My Apps")
CRYPTOBOT_TOKEN = "554603:AAoJCtxFiCgxpUiQAWVNUi6bF4q7zbcThyy"

# 🌐 URL API CryptoBot (не менять)
CRYPTOBOT_API_URL = "https://pay.crypt.bot/api"

# 💰 Валюта для оплаты через CryptoBot
# Доступные значения: USDT, TON, BTC, ETH, LTC, BNB, TRX, USDC
CRYPTOBOT_ASSET = "USDT"

# ⭐ Цена одной звезды Telegram в USD (рыночная: 0.013–0.015)
# Используется для авто-конвертации USDT → Stars
STARS_PRICE_USD = 0.014

# 🎁 Реферальное вознаграждение в USDT за каждого нового пользователя
REF_BONUS_USDT = 0.2

# 📦 Настройки каталога
PRODUCTS_PER_PAGE = 15
SHUFFLE_PRODUCTS = True

# 👤 Username администратора для приёма звёзд (без @)
ADMIN_STARS_USERNAME = "Id19911"

# 📢 Каналы для обязательной подписки
REQUIRED_CHANNELS = [
    {
        "title": "📢 Наш канал",
        "url": "https://t.me/resfsfsef",
        "id": -1003876663887
    },
    # Добавь ещё каналы по аналогии:
    # {
    #     "title": "📢 Второй канал",
    #     "url": "https://t.me/ещё_канал",
    #     "id": -100XXXXXXXXXX
    # },
]

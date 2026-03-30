import asyncio
import logging
import sqlite3
import json
from datetime import datetime, timedelta
from typing import Optional
import base64

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    CallbackQuery, Message
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ══════════════════════════════════════════════
# ⚙️ КОНФИГУРАЦИЯ — ЗАПОЛНИ СВОИ ДАННЫЕ
# ══════════════════════════════════════════════

BOT_TOKEN = "8602705022:AAE7_Q9H42YfXE1aFF2kHuGV4-dnRXrk_Bo"

# ID администраторов (можно несколько)
ADMIN_IDS = [6893832048]  # Замени на свои Telegram ID

# Каналы для обязательной подписки
# Формат: {"title": "Название", "url": "https://t.me/resfsfsef", "id": -1003876663887}
REQUIRED_CHANNELS = [
    {
        "title": "📢 Наш канал",
        "url": "https://t.me/resfsfsef",
        "id": -1003876663887  # ID канала (с минусом)
    },
    # Добавь ещё каналы при необходимости:
    # {
    #     "title": "💎 VIP канал",
    #     "url": "https://t.me/your_vip_channel",
    #     "id": -1009876543210
    # },
]

# ══════════════════════════════════════════════
# 📊 БАЗА ДАННЫХ
# ══════════════════════════════════════════════

def init_db():
    conn = sqlite3.connect("bot_database.db")
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id     INTEGER PRIMARY KEY,
            username    TEXT,
            full_name   TEXT,
            joined_at   TEXT,
            is_banned   INTEGER DEFAULT 0,
            mute_until  TEXT,
            ref_by      INTEGER
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS channels (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            title   TEXT,
            url     TEXT,
            chan_id INTEGER UNIQUE
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS broadcasts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            text        TEXT,
            buttons     TEXT,
            sent_at     TEXT,
            sent_count  INTEGER DEFAULT 0
        )
    """)

    # НОВАЯ ТАБЛИЦА — КАТАЛОГ (40 товаров)
    c.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id            INTEGER PRIMARY KEY,
            name          TEXT,
            description   TEXT,
            price_stars   INTEGER DEFAULT 0,
            active        INTEGER DEFAULT 1
        )
    """)

    conn.commit()
    conn.close()

def db():
    return sqlite3.connect("bot_database.db")

def add_user(user_id, username, full_name, ref_by=None):
    with db() as conn:
        conn.execute("""
            INSERT OR IGNORE INTO users (user_id, username, full_name, joined_at, ref_by)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, username, full_name, datetime.now().isoformat(), ref_by))

def get_user(user_id):
    with db() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        if row:
            return {
                "user_id": row[0], "username": row[1], "full_name": row[2],
                "joined_at": row[3], "is_banned": row[4], "mute_until": row[5],
                "ref_by": row[6]
            }
    return None

def get_all_users():
    with db() as conn:
        return conn.execute("SELECT user_id FROM users WHERE is_banned=0").fetchall()

def get_stats():
    with db() as conn:
        total  = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        banned = conn.execute("SELECT COUNT(*) FROM users WHERE is_banned=1").fetchone()[0]
        today  = conn.execute(
            "SELECT COUNT(*) FROM users WHERE joined_at >= ?",
            ((datetime.now() - timedelta(days=1)).isoformat(),)
        ).fetchone()[0]
        return {"total": total, "banned": banned, "today": today}

def ban_user(user_id):
    with db() as conn:
        conn.execute("UPDATE users SET is_banned=1 WHERE user_id=?", (user_id,))

def unban_user(user_id):
    with db() as conn:
        conn.execute("UPDATE users SET is_banned=0 WHERE user_id=?", (user_id,))

def mute_user(user_id, minutes):
    until = (datetime.now() + timedelta(minutes=minutes)).isoformat()
    with db() as conn:
        conn.execute("UPDATE users SET mute_until=? WHERE user_id=?", (until, user_id))

def unmute_user(user_id):
    with db() as conn:
        conn.execute("UPDATE users SET mute_until=NULL WHERE user_id=?", (user_id,))

def is_muted(user_id):
    with db() as conn:
        row = conn.execute("SELECT mute_until FROM users WHERE user_id=?", (user_id,)).fetchone()
        if row and row[0]:
            return datetime.fromisoformat(row[0]) > datetime.now()
    return False

def get_channels():
    with db() as conn:
        rows = conn.execute("SELECT * FROM channels").fetchall()
        return [{"id": r[0], "title": r[1], "url": r[2], "chan_id": r[3]} for r in rows]

def add_channel(title, url, chan_id):
    with db() as conn:
        conn.execute("INSERT OR REPLACE INTO channels (title, url, chan_id) VALUES (?,?,?)",
                     (title, url, chan_id))

def remove_channel(chan_id):
    with db() as conn:
        conn.execute("DELETE FROM channels WHERE id=?", (chan_id,))

def save_broadcast(text, buttons, sent_count):
    with db() as conn:
        conn.execute("INSERT INTO broadcasts (text,buttons,sent_at,sent_count) VALUES (?,?,?,?)",
                     (text, json.dumps(buttons), datetime.now().isoformat(), sent_count))

# Новые функции для каталога
def get_product(product_id: int):
    with db() as conn:
        row = conn.execute(
            "SELECT id, name, description, price_stars FROM products WHERE id=?",
            (product_id,)
        ).fetchone()
        if row:
            return {
                "id": row[0],
                "name": row[1] or f"Товар №{row[0]}",
                "description": row[2] or "",
                "price_stars": row[3] or 0
            }
    return None

def get_catalog_page(page: int = 1, per_page: int = 10):
    offset = (page - 1) * per_page
    with db() as conn:
        rows = conn.execute(
            "SELECT id, name FROM products ORDER BY id LIMIT ? OFFSET ?",
            (per_page, offset)
        ).fetchall()
    return rows

# ══════════════════════════════════════════════
# 🎛️ FSM СОСТОЯНИЯ
# ══════════════════════════════════════════════

class AdminStates(StatesGroup):
    # Рассылка
    broadcast_text    = State()
    broadcast_buttons = State()
    broadcast_confirm = State()

    # Добавление канала
    add_chan_title = State()
    add_chan_url   = State()
    add_chan_id    = State()

    # Бан / Мут
    ban_user_id   = State()
    unban_user_id = State()
    mute_user_id  = State()
    mute_duration = State()
    unmute_user_id = State()

    # Проверка юзера
    check_user_id = State()

# Новые состояния для пользователей
class UserStates(StatesGroup):
    wait_screenshot = State()   # ожидание скрина оплаты звёздами

class CryptoStates(StatesGroup):
    encrypt = State()
    decrypt = State()

# ══════════════════════════════════════════════
# 🔑 ИНИЦИАЛИЗАЦИЯ
# ══════════════════════════════════════════════

logging.basicConfig(level=logging.INFO)
init_db()

# Загружаем каналы из конфига в БД при первом запуске
for ch in REQUIRED_CHANNELS:
    add_channel(ch["title"], ch["url"], ch["id"])

# Инициализация 40 пустых товаров (при первом запуске)
with db() as conn:
    for i in range(1, 41):
        conn.execute(
            "INSERT OR IGNORE INTO products (id, name, description, price_stars, active) "
            "VALUES (?, ?, ?, ?, ?)",
            (i, f"Пустой товар {i}", "", 0, 0)
        )
    conn.commit()

bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher(storage=MemoryStorage())

# ══════════════════════════════════════════════
# 🛡️ ХЕЛПЕРЫ
# ══════════════════════════════════════════════

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

async def check_subscription(user_id: int) -> list:
    """Возвращает список каналов, на которые юзер НЕ подписан"""
    not_subscribed = []
    channels = get_channels()
    for ch in channels:
        try:
            member = await bot.get_chat_member(ch["chan_id"], user_id)
            if member.status in ("left", "kicked", "banned"):
                not_subscribed.append(ch)
        except Exception:
            not_subscribed.append(ch)
    return not_subscribed

def sub_keyboard(missing: list) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for ch in missing:
        kb.row(InlineKeyboardButton(text=f"📢 {ch['title']}", url=ch["url"]))
    kb.row(InlineKeyboardButton(text="✅ Я подписался!", callback_data="check_sub"))
    return kb.as_markup()

# ══════════════════════════════════════════════
# 🏠 ГЛАВНОЕ МЕНЮ
# ══════════════════════════════════════════════

def main_menu(user_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if is_admin(user_id):
        kb.row(InlineKeyboardButton(text="⚙️ Админ панель", callback_data="admin_panel"))
    kb.row(InlineKeyboardButton(text="📦 Каталог", callback_data="catalog"))
    kb.row(InlineKeyboardButton(text="🔐 Шифрование текста", callback_data="encryption"))
    kb.row(InlineKeyboardButton(text="👤 Мой профиль", callback_data="my_profile"))
    kb.row(InlineKeyboardButton(text="ℹ️ О боте", callback_data="about"))
    return kb.as_markup()

WELCOME_TEXT = """
✨ <b>Добро пожаловать!</b>

Рады видеть тебя здесь 🎉

Используй меню ниже для навигации.
"""

# ══════════════════════════════════════════════
# 📬 /start
# ══════════════════════════════════════════════

@dp.message(CommandStart())
async def cmd_start(message: Message):
    user = message.from_user
    args = message.text.split()
    ref_by = int(args[1]) if len(args) > 1 and args[1].isdigit() else None

    add_user(user.id, user.username, user.full_name, ref_by)

    # Проверка бана
    u = get_user(user.id)
    if u and u["is_banned"]:
        await message.answer("🚫 Вы заблокированы в этом боте.")
        return

    # Проверка подписки
    missing = await check_subscription(user.id)
    if missing:
        await message.answer(
            "🔔 <b>Для использования бота необходимо подписаться на наши каналы:</b>\n\n"
            "После подписки нажмите <b>«✅ Я подписался!»</b>",
            reply_markup=sub_keyboard(missing),
            parse_mode="HTML"
        )
        return

    # Уведомление реферера (только если человек успешно прошёл подписку)
    if ref_by and ref_by != user.id:
        try:
            await bot.send_message(
                ref_by,
                f"🎉 <b>Новый реферал!</b>\n\n"
                f"Пользователь <b>{user.full_name}</b> (@{user.username or '—'}) "
                f"присоединился по вашей реферальной ссылке!",
                parse_mode="HTML"
            )
        except Exception:
            pass  # если реферер заблокировал бота — тихо

    await message.answer(WELCOME_TEXT, reply_markup=main_menu(user.id), parse_mode="HTML")


@dp.callback_query(F.data == "check_sub")
async def check_sub_callback(call: CallbackQuery):
    missing = await check_subscription(call.from_user.id)
    if missing:
        await call.answer("❌ Вы ещё не подписались на все каналы!", show_alert=True)
        await call.message.edit_reply_markup(reply_markup=sub_keyboard(missing))
    else:
        await call.message.edit_text(
            WELCOME_TEXT,
            reply_markup=main_menu(call.from_user.id),
            parse_mode="HTML"
        )
        await call.answer("✅ Отлично! Добро пожаловать!")


@dp.callback_query(F.data == "my_profile")
async def my_profile(call: CallbackQuery):
    u = get_user(call.from_user.id)
    if not u:
        await call.answer("Профиль не найден", show_alert=True)
        return
    muted = is_muted(call.from_user.id)
    text = (
        f"👤 <b>Ваш профиль</b>\n\n"
        f"🆔 ID: <code>{u['user_id']}</code>\n"
        f"🔖 Username: @{u['username'] or '—'}\n"
        f"📅 Регистрация: {u['joined_at'][:10]}\n"
    )
    if u.get("ref_by"):
        text += f"👥 Приглашён: <code>{u['ref_by']}</code>\n"
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🔗 Реферальная ссылка", callback_data="ref_link"))
    kb.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu"))
    await call.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")


@dp.callback_query(F.data == "ref_link")
async def ref_link(call: CallbackQuery):
    link = f"https://t.me/{(await bot.get_me()).username}?start={call.from_user.id}"
    await call.message.answer(f"🔗 Ваша реферальная ссылка:\n<code>{link}</code>", parse_mode="HTML")
    await call.answer()


@dp.callback_query(F.data == "about")
async def about(call: CallbackQuery):
    text = (
        "ℹ️ <b>О боте</b>\n\n"
        "Этот бот создан для управления сообществом."
    )
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu"))
    await call.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")


@dp.callback_query(F.data == "main_menu")
async def go_main_menu(call: CallbackQuery):
    await call.message.edit_text(WELCOME_TEXT, reply_markup=main_menu(call.from_user.id), parse_mode="HTML")

# ══════════════════════════════════════════════
# 📦 КАТАЛОГ (40 товаров)
# ══════════════════════════════════════════════

def catalog_keyboard(page: int = 1) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    rows = get_catalog_page(page)
    for pid, name in rows:
        display = name if name and not name.startswith("Пустой товар") else f"Товар №{pid}"
        kb.row(InlineKeyboardButton(text=display, callback_data=f"product_{pid}"))

    # Пагинация (всего 4 страницы по 10 товаров)
    if page > 1:
        kb.row(InlineKeyboardButton(text="⬅️ Предыдущая", callback_data=f"catalog_page_{page-1}"))
    if page < 4:
        kb.row(InlineKeyboardButton(text="Следующая ➡️", callback_data=f"catalog_page_{page+1}"))
    kb.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu"))
    return kb.as_markup()


@dp.callback_query(F.data == "catalog")
async def show_catalog(call: CallbackQuery):
    await call.message.edit_text(
        "📦 <b>Каталог товаров</b>\n\nСтраница 1/4\nВыберите товар:",
        reply_markup=catalog_keyboard(1),
        parse_mode="HTML"
    )


@dp.callback_query(F.data.startswith("catalog_page_"))
async def show_catalog_page(call: CallbackQuery):
    page = int(call.data.split("_")[-1])
    await call.message.edit_text(
        f"📦 <b>Каталог товаров</b>\n\nСтраница {page}/4\nВыберите товар:",
        reply_markup=catalog_keyboard(page),
        parse_mode="HTML"
    )


@dp.callback_query(F.data.startswith("product_"))
async def product_detail(call: CallbackQuery):
    pid = int(call.data.split("_")[1])
    prod = get_product(pid)
    if not prod:
        await call.answer("Товар не найден", show_alert=True)
        return

    text = (
        f"📦 <b>{prod['name']}</b>\n\n"
        f"{prod['description'] or 'Описание будет добавлено позже'}\n\n"
        f"💰 Цена: <b>{prod['price_stars']} ⭐</b>\n\n"
        f"Выберите способ оплаты:"
    )
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="⭐ Оплата звёздами", callback_data=f"pay_stars_{pid}"))
    kb.row(InlineKeyboardButton(text="💎 Cryptobot", callback_data=f"pay_crypto_{pid}"))
    kb.row(InlineKeyboardButton(text="🔙 Назад в каталог", callback_data="catalog"))
    await call.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")


# Оплата звездами — запрос скрина
@dp.callback_query(F.data.startswith("pay_stars_"))
async def start_pay_stars(call: CallbackQuery, state: FSMContext):
    pid = int(call.data.split("_")[2])
    prod = get_product(pid)
    if not prod or prod["price_stars"] <= 0:
        await call.answer("❌ Цена не установлена для этого товара!", show_alert=True)
        return

    text = (
        f"⭐ <b>Оплата звездами</b>\n\n"
        f"Товар: <b>{prod['name']}</b>\n"
        f"Сумма: <b>{prod['price_stars']} ⭐</b>\n\n"
        f"1. Отправьте {prod['price_stars']} Telegram Stars администратору.\n"
        f"2. После оплаты пришлите скриншот оплаты сюда.\n\n"
        f"<i>Укажите в комментарии к оплате ваш ID: {call.from_user.id}</i>"
    )
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="❌ Отмена", callback_data=f"product_{pid}"))
    await call.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await state.set_state(UserStates.wait_screenshot)
    await state.update_data(pid=pid)


@dp.message(UserStates.wait_screenshot, F.photo)
async def handle_screenshot(message: Message, state: FSMContext):
    data = await state.get_data()
    pid = data.get("pid")
    if not pid:
        await state.clear()
        return

    prod = get_product(pid)
    user = message.from_user

    caption = (
        f"🛍️ <b>Новая оплата звездами на проверку!</b>\n\n"
        f"Товар: <b>{prod['name']}</b> (ID: {pid})\n"
        f"Сумма: {prod['price_stars']} ⭐\n"
        f"Пользователь: <a href='tg://user?id={user.id}'>{user.full_name}</a> "
        f"(@{user.username or '—'})\n"
        f"ID: <code>{user.id}</code>"
    )

    for admin_id in ADMIN_IDS:
        try:
            await bot.forward_message(
                chat_id=admin_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id
            )
            await bot.send_message(admin_id, caption, parse_mode="HTML")
        except Exception:
            pass

    await message.answer(
        "✅ Скриншот отправлен администраторам на проверку!\n"
        "После подтверждения товар будет выдан."
    )
    await state.clear()


@dp.message(UserStates.wait_screenshot)
async def handle_not_photo(message: Message, state: FSMContext):
    await message.answer("❌ Пожалуйста, отправьте <b>скриншот оплаты</b> (фото).", parse_mode="HTML")


# Оплата Cryptobot (заглушка — можно расширить позже)
@dp.callback_query(F.data.startswith("pay_crypto_"))
async def pay_crypto(call: CallbackQuery):
    pid = int(call.data.split("_")[2])
    prod = get_product(pid)
    text = (
        f"💎 <b>Оплата через Cryptobot</b>\n\n"
        f"Товар: <b>{prod['name']}</b>\n\n"
        f"Перейдите в @cryptobot и оплатите товар.\n"
        f"После оплаты (по желанию) можете прислать скриншот для подтверждения."
    )
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🔙 Назад к товару", callback_data=f"product_{pid}"))
    await call.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")

# ══════════════════════════════════════════════
# 🔐 ШИФРОВАНИЕ ТЕКСТА
# ══════════════════════════════════════════════

@dp.callback_query(F.data == "encryption")
async def show_encryption_menu(call: CallbackQuery):
    text = "🔐 <b>Шифрование текста в боте</b>\n\nВыберите действие:"
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🔒 Зашифровать", callback_data="start_encrypt"))
    kb.row(InlineKeyboardButton(text="🔓 Расшифровать", callback_data="start_decrypt"))
    kb.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu"))
    await call.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")


@dp.callback_query(F.data == "start_encrypt")
async def start_encrypt(call: CallbackQuery, state: FSMContext):
    await state.set_state(CryptoStates.encrypt)
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="❌ Отмена", callback_data="encryption"))
    await call.message.edit_text(
        "🔒 <b>Зашифровать текст</b>\n\nВведите текст, который нужно зашифровать:",
        reply_markup=kb.as_markup(), parse_mode="HTML"
    )


@dp.callback_query(F.data == "start_decrypt")
async def start_decrypt(call: CallbackQuery, state: FSMContext):
    await state.set_state(CryptoStates.decrypt)
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="❌ Отмена", callback_data="encryption"))
    await call.message.edit_text(
        "🔓 <b>Расшифровать текст</b>\n\nВведите зашифрованный текст (Base64):",
        reply_markup=kb.as_markup(), parse_mode="HTML"
    )


@dp.message(CryptoStates.encrypt)
async def process_encrypt(message: Message, state: FSMContext):
    try:
        encrypted = base64.urlsafe_b64encode(message.text.encode("utf-8")).decode("utf-8")
        await message.answer(
            f"🔒 <b>Зашифровано (Base64 URL-safe):</b>\n\n"
            f"<code>{encrypted}</code>\n\n"
            f"Скопируйте и используйте кнопку «Расшифровать» позже.",
            parse_mode="HTML"
        )
    except Exception:
        await message.answer("❌ Ошибка при шифровании.")
    await state.clear()


@dp.message(CryptoStates.decrypt)
async def process_decrypt(message: Message, state: FSMContext):
    try:
        decrypted = base64.urlsafe_b64decode(message.text.encode("utf-8")).decode("utf-8")
        await message.answer(
            f"🔓 <b>Расшифровано:</b>\n\n"
            f"<code>{decrypted}</code>",
            parse_mode="HTML"
        )
    except Exception:
        await message.answer("❌ Ошибка расшифровки. Убедитесь, что текст корректный Base64.")
    await state.clear()

# ══════════════════════════════════════════════
# 👑 АДМИН ПАНЕЛЬ
# ══════════════════════════════════════════════
# (весь блок админ-панели остался без изменений)

def admin_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"),
        InlineKeyboardButton(text="📢 Рассылка",   callback_data="admin_broadcast")
    )
    kb.row(
        InlineKeyboardButton(text="🚫 Бан",         callback_data="admin_ban"),
        InlineKeyboardButton(text="✅ Разбан",       callback_data="admin_unban")
    )
    kb.row(
        InlineKeyboardButton(text="🔇 Мут",         callback_data="admin_mute"),
        InlineKeyboardButton(text="🔊 Размут",       callback_data="admin_unmute")
    )
    kb.row(
        InlineKeyboardButton(text="📺 Каналы",       callback_data="admin_channels"),
        InlineKeyboardButton(text="🔍 Проверить юзера", callback_data="admin_check_user")
    )
    kb.row(InlineKeyboardButton(text="🏠 В главное меню", callback_data="main_menu"))
    return kb.as_markup()


@dp.callback_query(F.data == "admin_panel")
async def admin_panel(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("🚫 Нет доступа!", show_alert=True)
        return
    stats = get_stats()
    text = (
        "👑 <b>Панель администратора</b>\n\n"
        f"👥 Пользователей: <b>{stats['total']}</b>\n"
        f"🚫 Заблокировано: <b>{stats['banned']}</b>\n"
        f"🆕 За сутки: <b>{stats['today']}</b>\n\n"
        "Выберите действие:"
    )
    await call.message.edit_text(text, reply_markup=admin_keyboard(), parse_mode="HTML")


# ── Статистика ──────────────────────────────

@dp.callback_query(F.data == "admin_stats")
async def admin_stats(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer("🚫", show_alert=True)
    stats = get_stats()
    channels = get_channels()
    ch_list = "\n".join([f"  • {c['title']}" for c in channels]) or "  — нет каналов"
    text = (
        "📊 <b>Статистика бота</b>\n\n"
        f"👥 Всего пользователей: <b>{stats['total']}</b>\n"
        f"🚫 Заблокированных: <b>{stats['banned']}</b>\n"
        f"🆕 Новых за 24ч: <b>{stats['today']}</b>\n"
        f"📺 Подключённых каналов: <b>{len(channels)}</b>\n\n"
        f"<b>Каналы:</b>\n{ch_list}"
    )
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel"))
    await call.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")


# ── Управление каналами ──────────────────────

@dp.callback_query(F.data == "admin_channels")
async def admin_channels(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer("🚫", show_alert=True)
    channels = get_channels()
    kb = InlineKeyboardBuilder()
    for ch in channels:
        kb.row(InlineKeyboardButton(text=f"❌ Удалить «{ch['title']}»", callback_data=f"del_chan_{ch['id']}"))
    kb.row(InlineKeyboardButton(text="➕ Добавить канал", callback_data="add_channel"))
    kb.row(InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel"))
    text = "📺 <b>Управление каналами</b>\n\nПодключённые каналы:"
    if not channels:
        text += "\n\n<i>Каналов нет. Добавьте первый!</i>"
    await call.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")


@dp.callback_query(F.data.startswith("del_chan_"))
async def del_channel(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer("🚫", show_alert=True)
    chan_db_id = int(call.data.split("_")[2])
    remove_channel(chan_db_id)
    await call.answer("✅ Канал удалён!")
    await admin_channels(call)


@dp.callback_query(F.data == "add_channel")
async def add_channel_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer("🚫", show_alert=True)
    await state.set_state(AdminStates.add_chan_title)
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="❌ Отмена", callback_data="admin_channels"))
    await call.message.edit_text(
        "📺 <b>Добавление канала</b>\n\nВведите <b>название</b> канала:",
        reply_markup=kb.as_markup(), parse_mode="HTML"
    )


@dp.message(AdminStates.add_chan_title)
async def add_channel_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text)
    await state.set_state(AdminStates.add_chan_url)
    await message.answer("🔗 Введите <b>ссылку</b> на канал[](https://t.me/...):", parse_mode="HTML")


@dp.message(AdminStates.add_chan_url)
async def add_channel_url(message: Message, state: FSMContext):
    await state.update_data(url=message.text)
    await state.set_state(AdminStates.add_chan_id)
    await message.answer(
        "🆔 Введите <b>ID канала</b> (например: -1001234567890)\n\n"
        "<i>Как узнать ID? Перешли любое сообщение из канала боту @username_to_id_bot</i>",
        parse_mode="HTML"
    )


@dp.message(AdminStates.add_chan_id)
async def add_channel_id(message: Message, state: FSMContext):
    if not message.text.lstrip("-").isdigit():
        await message.answer("❌ Неверный формат ID. Введите числовой ID:")
        return
    data = await state.get_data()
    add_channel(data["title"], data["url"], int(message.text))
    await state.clear()
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="📺 К каналам", callback_data="admin_channels"))
    kb.row(InlineKeyboardButton(text="👑 Админ панель", callback_data="admin_panel"))
    await message.answer(
        f"✅ Канал <b>{data['title']}</b> успешно добавлен!",
        reply_markup=kb.as_markup(), parse_mode="HTML"
    )


# ── Бан ────────────────────────────────────

@dp.callback_query(F.data == "admin_ban")
async def admin_ban_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer("🚫", show_alert=True)
    await state.set_state(AdminStates.ban_user_id)
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="❌ Отмена", callback_data="admin_panel"))
    await call.message.edit_text(
        "🚫 <b>Бан пользователя</b>\n\nВведите <b>ID</b> пользователя:",
        reply_markup=kb.as_markup(), parse_mode="HTML"
    )


@dp.message(AdminStates.ban_user_id)
async def do_ban(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Введите числовой ID:")
        return
    uid = int(message.text)
    ban_user(uid)
    await state.clear()
    try:
        await bot.send_message(uid, "🚫 Вы были заблокированы администратором.")
    except Exception:
        pass
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="👑 Админ панель", callback_data="admin_panel"))
    await message.answer(
        f"✅ Пользователь <code>{uid}</code> заблокирован.",
        reply_markup=kb.as_markup(), parse_mode="HTML"
    )


@dp.callback_query(F.data == "admin_unban")
async def admin_unban_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer("🚫", show_alert=True)
    await state.set_state(AdminStates.unban_user_id)
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="❌ Отмена", callback_data="admin_panel"))
    await call.message.edit_text(
        "✅ <b>Разбан пользователя</b>\n\nВведите <b>ID</b> пользователя:",
        reply_markup=kb.as_markup(), parse_mode="HTML"
    )


@dp.message(AdminStates.unban_user_id)
async def do_unban(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Введите числовой ID:")
        return
    uid = int(message.text)
    unban_user(uid)
    await state.clear()
    try:
        await bot.send_message(uid, "✅ Ваша блокировка снята! Добро пожаловать обратно.")
    except Exception:
        pass
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="👑 Админ панель", callback_data="admin_panel"))
    await message.answer(
        f"✅ Пользователь <code>{uid}</code> разблокирован.",
        reply_markup=kb.as_markup(), parse_mode="HTML"
    )


# ── Мут ────────────────────────────────────

@dp.callback_query(F.data == "admin_mute")
async def admin_mute_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer("🚫", show_alert=True)
    await state.set_state(AdminStates.mute_user_id)
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="❌ Отмена", callback_data="admin_panel"))
    await call.message.edit_text(
        "🔇 <b>Мут пользователя</b>\n\nВведите <b>ID</b> пользователя:",
        reply_markup=kb.as_markup(), parse_mode="HTML"
    )


@dp.message(AdminStates.mute_user_id)
async def mute_get_id(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Введите числовой ID:")
        return
    await state.update_data(mute_uid=int(message.text))
    await state.set_state(AdminStates.mute_duration)
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="15 мин",  callback_data="mute_15"),
        InlineKeyboardButton(text="1 час",   callback_data="mute_60"),
        InlineKeyboardButton(text="1 день",  callback_data="mute_1440")
    )
    kb.row(InlineKeyboardButton(text="Своё время (минуты)", callback_data="mute_custom"))
    await message.answer("⏱ Выберите длительность мута:", reply_markup=kb.as_markup())


@dp.callback_query(F.data.startswith("mute_"))
async def mute_duration_cb(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    uid = data.get("mute_uid")
    if not uid:
        return await call.answer("Ошибка")

    dur_map = {"mute_15": 15, "mute_60": 60, "mute_1440": 1440}
    if call.data in dur_map:
        minutes = dur_map[call.data]
        mute_user(uid, minutes)
        await state.clear()
        try:
            await bot.send_message(uid, f"🔇 Вы были замучены на {minutes} минут.")
        except Exception:
            pass
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="👑 Админ панель", callback_data="admin_panel"))
        await call.message.edit_text(
            f"✅ Пользователь <code>{uid}</code> замучен на {minutes} минут.",
            reply_markup=kb.as_markup(), parse_mode="HTML"
        )
    elif call.data == "mute_custom":
        await call.message.edit_text("⏱ Введите количество минут:")
        await call.answer()


@dp.message(AdminStates.mute_duration)
async def mute_duration_text(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Введите число (минуты):")
        return
    data = await state.get_data()
    uid = data["mute_uid"]
    minutes = int(message.text)
    mute_user(uid, minutes)
    await state.clear()
    try:
        await bot.send_message(uid, f"🔇 Вы были замучены на {minutes} минут.")
    except Exception:
        pass
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="👑 Админ панель", callback_data="admin_panel"))
    await message.answer(
        f"✅ Пользователь <code>{uid}</code> замучен на {minutes} минут.",
        reply_markup=kb.as_markup(), parse_mode="HTML"
    )


@dp.callback_query(F.data == "admin_unmute")
async def admin_unmute_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer("🚫", show_alert=True)
    await state.set_state(AdminStates.unmute_user_id)
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="❌ Отмена", callback_data="admin_panel"))
    await call.message.edit_text(
        "🔊 <b>Размут пользователя</b>\n\nВведите <b>ID</b> пользователя:",
        reply_markup=kb.as_markup(), parse_mode="HTML"
    )


@dp.message(AdminStates.unmute_user_id)
async def do_unmute(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Введите числовой ID:")
        return
    uid = int(message.text)
    unmute_user(uid)
    await state.clear()
    try:
        await bot.send_message(uid, "🔊 Ваш мут был снят!")
    except Exception:
        pass
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="👑 Админ панель", callback_data="admin_panel"))
    await message.answer(
        f"✅ Мут пользователя <code>{uid}</code> снят.",
        reply_markup=kb.as_markup(), parse_mode="HTML"
    )


# ── Проверка пользователя ──────────────────

@dp.callback_query(F.data == "admin_check_user")
async def admin_check_user_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer("🚫", show_alert=True)
    await state.set_state(AdminStates.check_user_id)
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="❌ Отмена", callback_data="admin_panel"))
    await call.message.edit_text(
        "🔍 <b>Проверка пользователя</b>\n\nВведите <b>ID</b>:",
        reply_markup=kb.as_markup(), parse_mode="HTML"
    )


@dp.message(AdminStates.check_user_id)
async def do_check_user(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("❌ Введите числовой ID:")
        return
    uid = int(message.text)
    u = get_user(uid)
    await state.clear()
    if not u:
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel"))
        await message.answer(f"❌ Пользователь <code>{uid}</code> не найден.", reply_markup=kb.as_markup(), parse_mode="HTML")
        return

    muted = is_muted(uid)
    text = (
        f"🔍 <b>Информация о пользователе</b>\n\n"
        f"🆔 ID: <code>{u['user_id']}</code>\n"
        f"📛 Имя: {u['full_name']}\n"
        f"🔖 Username: @{u['username'] or '—'}\n"
        f"📅 Регистрация: {u['joined_at'][:10]}\n"
        f"🚫 Бан: {'Да' if u['is_banned'] else 'Нет'}\n"
        f"🔇 Мут: {'Да' if muted else 'Нет'}\n"
    )
    kb = InlineKeyboardBuilder()
    if u["is_banned"]:
        kb.row(InlineKeyboardButton(text="✅ Разбанить", callback_data=f"quick_unban_{uid}"))
    else:
        kb.row(InlineKeyboardButton(text="🚫 Забанить", callback_data=f"quick_ban_{uid}"))
    if muted:
        kb.row(InlineKeyboardButton(text="🔊 Размутить", callback_data=f"quick_unmute_{uid}"))
    else:
        kb.row(InlineKeyboardButton(text="🔇 Замутить на 1ч", callback_data=f"quick_mute_{uid}"))
    kb.row(InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel"))
    await message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")


@dp.callback_query(F.data.startswith("quick_ban_"))
async def quick_ban(call: CallbackQuery):
    uid = int(call.data.split("_")[2])
    ban_user(uid)
    await call.answer(f"✅ Пользователь {uid} забанен!")
    try:
        await bot.send_message(uid, "🚫 Вы были заблокированы администратором.")
    except Exception:
        pass


@dp.callback_query(F.data.startswith("quick_unban_"))
async def quick_unban(call: CallbackQuery):
    uid = int(call.data.split("_")[2])
    unban_user(uid)
    await call.answer(f"✅ Пользователь {uid} разбанен!")
    try:
        await bot.send_message(uid, "✅ Ваша блокировка снята!")
    except Exception:
        pass


@dp.callback_query(F.data.startswith("quick_mute_"))
async def quick_mute(call: CallbackQuery):
    uid = int(call.data.split("_")[2])
    mute_user(uid, 60)
    await call.answer(f"✅ Пользователь {uid} замучен на 1 час!")
    try:
        await bot.send_message(uid, "🔇 Вы замучены на 1 час.")
    except Exception:
        pass


@dp.callback_query(F.data.startswith("quick_unmute_"))
async def quick_unmute(call: CallbackQuery):
    uid = int(call.data.split("_")[2])
    unmute_user(uid)
    await call.answer(f"✅ Мут пользователя {uid} снят!")
    try:
        await bot.send_message(uid, "🔊 Ваш мут снят!")
    except Exception:
        pass


# ══════════════════════════════════════════════
# 📢 РАССЫЛКА
# ══════════════════════════════════════════════

@dp.callback_query(F.data == "admin_broadcast")
async def broadcast_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer("🚫", show_alert=True)
    await state.set_state(AdminStates.broadcast_text)
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="❌ Отмена", callback_data="admin_panel"))
    await call.message.edit_text(
        "📢 <b>Умная рассылка</b>\n\n"
        "Введите текст сообщения для рассылки.\n"
        "<i>Поддерживается HTML разметка: <b>жирный</b>, <i>курсив</i>, <code>код</code>, ссылки</i>",
        reply_markup=kb.as_markup(), parse_mode="HTML"
    )


@dp.message(AdminStates.broadcast_text)
async def broadcast_get_text(message: Message, state: FSMContext):
    await state.update_data(broadcast_text=message.text, broadcast_html=message.html_text)
    await state.set_state(AdminStates.broadcast_buttons)
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="⏭ Пропустить кнопки", callback_data="skip_buttons"))
    await message.answer(
        "🔘 <b>Добавить кнопки?</b>\n\n"
        "Введите кнопки в формате:\n"
        "<code>Текст кнопки | https://ссылка</code>\n\n"
        "Каждая кнопка — на отдельной строке.\n"
        "Пример:\n"
        "<code>🌟 Наш сайт | https://example.com\n"
        "💎 VIP канал | https://t.me/vip</code>",
        reply_markup=kb.as_markup(), parse_mode="HTML"
    )


@dp.callback_query(F.data == "skip_buttons")
async def skip_buttons(call: CallbackQuery, state: FSMContext):
    await state.update_data(buttons=[])
    await state.set_state(AdminStates.broadcast_confirm)
    data = await state.get_data()
    await show_broadcast_preview(call.message, data, state)


@dp.message(AdminStates.broadcast_buttons)
async def broadcast_get_buttons(message: Message, state: FSMContext):
    buttons = []
    lines = message.text.strip().split("\n")
    errors = []
    for i, line in enumerate(lines):
        if "|" not in line:
            errors.append(f"Строка {i+1}: нет символа '|'")
            continue
        parts = line.split("|", 1)
        btn_text = parts[0].strip()
        btn_url  = parts[1].strip()
        if not btn_url.startswith("http"):
            errors.append(f"Строка {i+1}: некорректная ссылка")
            continue
        buttons.append({"text": btn_text, "url": btn_url})

    if errors:
        await message.answer(
            "⚠️ <b>Ошибки в кнопках:</b>\n" + "\n".join(errors) + "\n\nПопробуйте ещё раз:",
            parse_mode="HTML"
        )
        return

    await state.update_data(buttons=buttons)
    await state.set_state(AdminStates.broadcast_confirm)
    data = await state.get_data()
    await show_broadcast_preview(message, data, state)


async def show_broadcast_preview(message: Message, data: dict, state: FSMContext):
    buttons = data.get("buttons", [])
    text = data.get("broadcast_html") or data.get("broadcast_text", "")
    stats = get_stats()

    preview_kb = InlineKeyboardBuilder()
    for btn in buttons:
        preview_kb.row(InlineKeyboardButton(text=btn["text"], url=btn["url"]))

    if buttons:
        await message.answer(
            "👁 <b>Предпросмотр сообщения:</b>",
            parse_mode="HTML"
        )
        await message.answer(text, reply_markup=preview_kb.as_markup(), parse_mode="HTML")
    else:
        await message.answer("👁 <b>Предпросмотр:</b>", parse_mode="HTML")
        await message.answer(text, parse_mode="HTML")

    confirm_kb = InlineKeyboardBuilder()
    confirm_kb.row(
        InlineKeyboardButton(
            text=f"✅ Отправить ({stats['total'] - stats['banned']} юзеров)",
            callback_data="confirm_broadcast"
        )
    )
    confirm_kb.row(InlineKeyboardButton(text="❌ Отмена", callback_data="admin_panel"))
    await message.answer(
        f"📊 Получателей: <b>{stats['total'] - stats['banned']}</b>\n"
        f"🔘 Кнопок: <b>{len(buttons)}</b>",
        reply_markup=confirm_kb.as_markup(), parse_mode="HTML"
    )


@dp.callback_query(F.data == "confirm_broadcast")
async def confirm_broadcast(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer("🚫", show_alert=True)

    data = await state.get_data()
    await state.clear()

    text    = data.get("broadcast_html") or data.get("broadcast_text", "")
    buttons = data.get("buttons", [])

    kb = None
    if buttons:
        bkb = InlineKeyboardBuilder()
        for btn in buttons:
            bkb.row(InlineKeyboardButton(text=btn["text"], url=btn["url"]))
        kb = bkb.as_markup()

    users = get_all_users()
    sent = 0
    failed = 0

    status_msg = await call.message.answer("📤 Отправляю рассылку...")

    for (uid,) in users:
        try:
            await bot.send_message(uid, text, reply_markup=kb, parse_mode="HTML")
            sent += 1
            if sent % 20 == 0:
                await status_msg.edit_text(f"📤 Отправлено: {sent}/{len(users)}...")
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)  # Антифлуд

    save_broadcast(text, buttons, sent)

    result_kb = InlineKeyboardBuilder()
    result_kb.row(InlineKeyboardButton(text="👑 Панель", callback_data="admin_panel"))
    await status_msg.edit_text(
        f"✅ <b>Рассылка завершена!</b>\n\n"
        f"📤 Отправлено: <b>{sent}</b>\n"
        f"❌ Ошибок: <b>{failed}</b>",
        reply_markup=result_kb.as_markup(), parse_mode="HTML"
    )
    await call.answer()


# ══════════════════════════════════════════════
# 🛡️ ФИЛЬТР МУТА ДЛЯ СООБЩЕНИЙ
# ══════════════════════════════════════════════

@dp.message()
async def message_filter(message: Message):
    if is_muted(message.from_user.id):
        await message.reply("🔇 Вы замучены и не можете отправлять сообщения.")
        return


# ══════════════════════════════════════════════
# 🚀 ЗАПУСК
# ══════════════════════════════════════════════

async def main():
    print("🤖 Бот запущен!")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())

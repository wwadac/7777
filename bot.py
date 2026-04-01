import asyncio
import logging
import sqlite3
import json
import re
from datetime import datetime, timedelta

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

from config import BOT_TOKEN, ADMIN_IDS, REQUIRED_CHANNELS, REF_BONUS_USDT

# ══════════════════════════════════════════════
# 🧩 МАСКИРОВКА ТЕКСТА
# ══════════════════════════════════════════════

HOMOGLYPHS = {
    'а': 'α', 'в': 'β', 'е': '℮', 'и': 'u', 'к': 'k', 'м': 'м', 'н': 'n',
    'о': 'ο', 'п': 'π', 'р': 'ρ', 'с': 'c', 'т': 'm', 'у': 'γ',
    'А': 'Α', 'В': 'Β', 'Е': '℮', 'И': 'U', 'К': 'K', 'М': 'М', 'Н': 'Н',
    'О': 'Ο', 'П': 'Π', 'Р': 'Ρ', 'С': 'C', 'Т': 'T', 'У': 'Υ'
}

def mask_text(text: str) -> str:
    """Заменяет кириллицу на гомоглифы, не трогая HTML-теги."""
    parts = re.split(r'(<[^>]*>)', text)
    result = []
    for part in parts:
        if part.startswith('<') and part.endswith('>'):
            result.append(part)
        else:
            result.append(''.join(HOMOGLYPHS.get(ch, ch) for ch in part))
    return ''.join(result)

async def safe_send_message(chat_id, text, **kwargs):
    masked = mask_text(str(text))
    return await bot.send_message(chat_id, masked, **kwargs)

async def safe_edit_message(message: Message, text, **kwargs):
    masked = mask_text(str(text))
    return await message.edit_text(masked, **kwargs)

# ══════════════════════════════════════════════
# 📊 БАЗА ДАННЫХ
# ══════════════════════════════════════════════

def init_db():
    conn = sqlite3.connect("bot_database.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id       INTEGER PRIMARY KEY,
            username      TEXT,
            full_name     TEXT,
            joined_at     TEXT,
            is_banned     INTEGER DEFAULT 0,
            mute_until    TEXT,
            ref_by        INTEGER,
            ref_count     INTEGER DEFAULT 0,
            ref_balance   REAL    DEFAULT 0.0
        )
    """)
    # Миграция: добавляем колонки если их нет (для уже существующих БД)
    for col, definition in [
        ("ref_count",   "INTEGER DEFAULT 0"),
        ("ref_balance", "REAL DEFAULT 0.0"),
    ]:
        try:
            c.execute(f"ALTER TABLE users ADD COLUMN {col} {definition}")
        except sqlite3.OperationalError:
            pass  # Колонка уже существует

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
    c.execute("""
        CREATE TABLE IF NOT EXISTS withdrawal_requests (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER,
            amount      REAL,
            status      TEXT DEFAULT 'pending',
            created_at  TEXT
        )
    """)
    conn.commit()
    conn.close()

def db():
    return sqlite3.connect("bot_database.db")

def add_user(user_id, username, full_name, ref_by=None) -> bool:
    """
    Добавляет пользователя. Возвращает True если пользователь НОВЫЙ.
    Если он новый и пришёл по реф-ссылке — начисляет бонус рефереру.
    """
    with db() as conn:
        cursor = conn.execute("""
            INSERT OR IGNORE INTO users (user_id, username, full_name, joined_at, ref_by)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, username, full_name, datetime.now().isoformat(), ref_by))
        is_new = cursor.rowcount > 0

        if is_new and ref_by and ref_by != user_id:
            # Начисляем бонус рефереру
            conn.execute("""
                UPDATE users
                SET ref_count = ref_count + 1,
                    ref_balance = ref_balance + ?
                WHERE user_id = ?
            """, (REF_BONUS_USDT, ref_by))

    return is_new

def get_user(user_id):
    with db() as conn:
        row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        if row:
            return {
                "user_id":     row[0],
                "username":    row[1],
                "full_name":   row[2],
                "joined_at":   row[3],
                "is_banned":   row[4],
                "mute_until":  row[5],
                "ref_by":      row[6],
                "ref_count":   row[7] if len(row) > 7 else 0,
                "ref_balance": row[8] if len(row) > 8 else 0.0,
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
        refs_total = conn.execute("SELECT COALESCE(SUM(ref_count),0) FROM users").fetchone()[0]
    return {"total": total, "banned": banned, "today": today, "refs_total": refs_total}

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
        conn.execute(
            "INSERT OR REPLACE INTO channels (title, url, chan_id) VALUES (?,?,?)",
            (title, url, chan_id)
        )

def remove_channel(chan_db_id):
    with db() as conn:
        conn.execute("DELETE FROM channels WHERE id=?", (chan_db_id,))

def save_broadcast(text, buttons, sent_count):
    with db() as conn:
        conn.execute(
            "INSERT INTO broadcasts (text,buttons,sent_at,sent_count) VALUES (?,?,?,?)",
            (text, json.dumps(buttons), datetime.now().isoformat(), sent_count)
        )

def create_withdrawal_request(user_id, amount) -> int:
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO withdrawal_requests (user_id, amount, status, created_at) VALUES (?,?,?,?)",
            (user_id, amount, 'pending', datetime.now().isoformat())
        )
        # Списываем баланс сразу
        conn.execute(
            "UPDATE users SET ref_balance = ref_balance - ? WHERE user_id=?",
            (amount, user_id)
        )
        return cur.lastrowid

# ══════════════════════════════════════════════
# 🎛️ FSM СОСТОЯНИЯ
# ══════════════════════════════════════════════

class AdminStates(StatesGroup):
    broadcast_text    = State()
    broadcast_confirm = State()
    add_chan_title     = State()
    add_chan_url       = State()
    add_chan_id        = State()
    ban_user_id        = State()
    unban_user_id      = State()
    mute_user_id       = State()
    mute_duration      = State()
    unmute_user_id     = State()
    check_user_id      = State()

# ══════════════════════════════════════════════
# 🔑 ИНИЦИАЛИЗАЦИЯ
# ══════════════════════════════════════════════

logging.basicConfig(level=logging.INFO)
init_db()

for ch in REQUIRED_CHANNELS:
    add_channel(ch["title"], ch["url"], ch["id"])

bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher(storage=MemoryStorage())

# ══════════════════════════════════════════════
# 🛡️ ХЕЛПЕРЫ
# ══════════════════════════════════════════════

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

async def check_subscription(user_id: int) -> list:
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
    kb.row(InlineKeyboardButton(text="📦 Каталог",         callback_data="catalog"))
    kb.row(InlineKeyboardButton(text="👤 Мой профиль",     callback_data="my_profile"))
    kb.row(InlineKeyboardButton(text="ℹ️ О боте",          callback_data="about"))
    return kb.as_markup()

WELCOME_TEXT = """
✨ <b>Добро пожаловать!</b>

Рады видеть тебя здесь 🎉

Используй меню ниже для навигации.
"""

# ══════════════════════════════════════════════
# 📬 /start  (с реферальной ссылкой)
# ══════════════════════════════════════════════

@dp.message(CommandStart())
async def cmd_start(message: Message):
    user = message.from_user
    args = message.text.split()
    ref_by = int(args[1]) if len(args) > 1 and args[1].isdigit() else None

    is_new = add_user(user.id, user.username, user.full_name, ref_by)

    # Уведомление реферера о новом приглашённом
    if is_new and ref_by and ref_by != user.id:
        try:
            await safe_send_message(
                ref_by,
                f"🎉 <b>По вашей реферальной ссылке зарегистрировался новый пользователь!</b>\n\n"
                f"👤 {user.full_name}\n"
                f"💰 Вам начислено: <b>+{REF_BONUS_USDT} USDT</b> на реферальный баланс\n\n"
                f"Смотрите баланс в разделе «👤 Мой профиль»",
                parse_mode="HTML"
            )
        except Exception:
            pass

        # Уведомление администраторам
        for admin_id in ADMIN_IDS:
            try:
                await safe_send_message(
                    admin_id,
                    f"🆕 <b>Новый реферал!</b>\n\n"
                    f"Пользователь: {user.full_name} (<code>{user.id}</code>)\n"
                    f"Пригласил: <code>{ref_by}</code>\n"
                    f"Бонус: +{REF_BONUS_USDT} USDT",
                    parse_mode="HTML"
                )
            except Exception:
                pass

    u = get_user(user.id)
    if u and u["is_banned"]:
        await safe_send_message(user.id, "🚫 Вы заблокированы в этом боте.")
        return

    missing = await check_subscription(user.id)
    if missing:
        await safe_send_message(
            user.id,
            "🔔 <b>Для использования бота необходимо подписаться на каналы:</b>\n\n"
            "После подписки нажмите <b>«✅ Я подписался!»</b>",
            reply_markup=sub_keyboard(missing),
            parse_mode="HTML"
        )
        return

    await safe_send_message(user.id, WELCOME_TEXT, reply_markup=main_menu(user.id), parse_mode="HTML")


@dp.callback_query(F.data == "check_sub")
async def check_sub_callback(call: CallbackQuery):
    missing = await check_subscription(call.from_user.id)
    if missing:
        await call.answer("❌ Вы ещё не подписались на все каналы!", show_alert=True)
        try:
            await safe_edit_message(call.message, call.message.html_text, reply_markup=sub_keyboard(missing))
        except Exception:
            pass
    else:
        await safe_edit_message(
            call.message, WELCOME_TEXT,
            reply_markup=main_menu(call.from_user.id),
            parse_mode="HTML"
        )
        await call.answer("✅ Отлично! Добро пожаловать!")


# ══════════════════════════════════════════════
# 👤 ПРОФИЛЬ (с реф. балансом)
# ══════════════════════════════════════════════

@dp.callback_query(F.data == "my_profile")
async def my_profile(call: CallbackQuery):
    u = get_user(call.from_user.id)
    if not u:
        await call.answer("Профиль не найден", show_alert=True)
        return

    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={call.from_user.id}"
    ref_count   = u.get("ref_count", 0)
    ref_balance = u.get("ref_balance", 0.0)

    text = (
        f"👤 <b>Ваш профиль</b>\n\n"
        f"🆔 ID: <code>{u['user_id']}</code>\n"
        f"🔖 Username: @{u['username'] or '—'}\n"
        f"📅 Регистрация: {u['joined_at'][:10]}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔗 <b>Реферальная программа</b>\n"
        f"👥 Приглашено: <b>{ref_count}</b> чел.\n"
        f"💰 Реф. баланс: <b>{ref_balance:.2f} USDT</b>\n"
        f"🎁 Бонус за реферала: +{REF_BONUS_USDT} USDT\n\n"
        f"🔗 Ваша ссылка:\n<code>{ref_link}</code>"
    )

    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🔗 Скопировать реф. ссылку", callback_data="ref_link"))
    if ref_balance >= REF_BONUS_USDT:
        kb.row(InlineKeyboardButton(
            text=f"💸 Вывести {ref_balance:.2f} USDT",
            callback_data="withdraw_ref_balance"
        ))
    kb.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu"))
    await safe_edit_message(call.message, text, reply_markup=kb.as_markup(), parse_mode="HTML")


@dp.callback_query(F.data == "ref_link")
async def ref_link(call: CallbackQuery):
    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start={call.from_user.id}"
    await safe_send_message(
        call.from_user.id,
        f"🔗 <b>Ваша реферальная ссылка:</b>\n\n<code>{link}</code>\n\n"
        f"💰 За каждого нового пользователя вы получаете <b>{REF_BONUS_USDT} USDT</b> на баланс.",
        parse_mode="HTML"
    )
    await call.answer()


@dp.callback_query(F.data == "withdraw_ref_balance")
async def withdraw_ref_balance(call: CallbackQuery):
    u = get_user(call.from_user.id)
    if not u:
        return await call.answer("❌ Профиль не найден", show_alert=True)

    balance = u.get("ref_balance", 0.0)
    if balance < REF_BONUS_USDT:
        return await call.answer(
            f"❌ Минимальная сумма вывода: {REF_BONUS_USDT} USDT\nВаш баланс: {balance:.2f} USDT",
            show_alert=True
        )

    req_id = create_withdrawal_request(call.from_user.id, balance)

    # Уведомляем всех администраторов
    for admin_id in ADMIN_IDS:
        try:
            await safe_send_message(
                admin_id,
                f"💸 <b>ЗАПРОС НА ВЫВОД РЕФЕРАЛЬНОГО БАЛАНСА</b>\n\n"
                f"👤 Пользователь: {call.from_user.full_name}\n"
                f"🔖 Username: @{call.from_user.username or '—'}\n"
                f"🆔 ID: <code>{call.from_user.id}</code>\n"
                f"💰 Сумма: <b>{balance:.2f} USDT</b>\n"
                f"🔢 Запрос №{req_id}\n\n"
                f"Переведите USDT пользователю вручную через CryptoBot или напрямую.",
                parse_mode="HTML"
            )
        except Exception as e:
            logging.error(f"Не удалось уведомить админа {admin_id}: {e}")

    await safe_edit_message(
        call.message,
        f"✅ <b>Запрос на вывод отправлен!</b>\n\n"
        f"💰 Сумма: <b>{balance:.2f} USDT</b>\n"
        f"🔢 Запрос №{req_id}\n\n"
        f"Администратор обработает ваш запрос в ближайшее время.",
        reply_markup=None, parse_mode="HTML"
    )
    await call.answer()


# ══════════════════════════════════════════════
# ℹ️ О БОТЕ
# ══════════════════════════════════════════════

@dp.callback_query(F.data == "about")
async def about(call: CallbackQuery):
    text = (
        "ℹ️ <b>О боте</b>\n\n"
        "Этот бот создан для управления сообществом и продажи товаров.\n\n"
        f"💰 <b>Реферальная программа:</b>\n"
        f"Приглашайте друзей по своей ссылке и получайте {REF_BONUS_USDT} USDT за каждого!"
    )
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu"))
    await safe_edit_message(call.message, text, reply_markup=kb.as_markup(), parse_mode="HTML")


@dp.callback_query(F.data == "main_menu")
async def go_main_menu(call: CallbackQuery):
    await safe_edit_message(
        call.message, WELCOME_TEXT,
        reply_markup=main_menu(call.from_user.id), parse_mode="HTML"
    )

# ══════════════════════════════════════════════
# 👑 АДМИН ПАНЕЛЬ
# ══════════════════════════════════════════════

def admin_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="📊 Статистика",          callback_data="admin_stats"),
        InlineKeyboardButton(text="📢 Рассылка",            callback_data="admin_broadcast")
    )
    kb.row(
        InlineKeyboardButton(text="🚫 Бан",                 callback_data="admin_ban"),
        InlineKeyboardButton(text="✅ Разбан",               callback_data="admin_unban")
    )
    kb.row(
        InlineKeyboardButton(text="🔇 Мут",                 callback_data="admin_mute"),
        InlineKeyboardButton(text="🔊 Размут",               callback_data="admin_unmute")
    )
    kb.row(
        InlineKeyboardButton(text="📺 Каналы",              callback_data="admin_channels"),
        InlineKeyboardButton(text="🔍 Проверить юзера",     callback_data="admin_check_user")
    )
    kb.row(
        InlineKeyboardButton(text="📦 Управление каталогом", callback_data="admin_manage_catalog")
    )
    kb.row(InlineKeyboardButton(text="🏠 В главное меню",   callback_data="main_menu"))
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
        f"🆕 За сутки: <b>{stats['today']}</b>\n"
        f"🔗 Всего рефералов: <b>{stats['refs_total']}</b>\n\n"
        "Выберите действие:"
    )
    await safe_edit_message(call.message, text, reply_markup=admin_keyboard(), parse_mode="HTML")


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
        f"🔗 Всего приглашено по рефкам: <b>{stats['refs_total']}</b>\n"
        f"📺 Подключённых каналов: <b>{len(channels)}</b>\n\n"
        f"<b>Каналы:</b>\n{ch_list}"
    )
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel"))
    await safe_edit_message(call.message, text, reply_markup=kb.as_markup(), parse_mode="HTML")


# ══════════════════════════════════════════════
# 📢 РАССЫЛКА
# ══════════════════════════════════════════════

@dp.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer("🚫", show_alert=True)
    await state.set_state(AdminStates.broadcast_text)
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="❌ Отмена", callback_data="admin_panel"))
    await safe_edit_message(
        call.message,
        "📢 <b>Рассылка</b>\n\nВведите текст рассылки (поддерживается HTML):",
        reply_markup=kb.as_markup(), parse_mode="HTML"
    )


@dp.message(AdminStates.broadcast_text)
async def broadcast_text_received(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.update_data(broadcast_text=message.text)
    await state.set_state(AdminStates.broadcast_confirm)
    users = get_all_users()
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="✅ Отправить", callback_data="broadcast_send"),
        InlineKeyboardButton(text="❌ Отмена",    callback_data="admin_panel")
    )
    await safe_send_message(
        message.chat.id,
        f"📢 <b>Предпросмотр рассылки:</b>\n\n{message.text}\n\n"
        f"👥 Получателей: <b>{len(users)}</b>\n\nОтправить?",
        reply_markup=kb.as_markup(), parse_mode="HTML"
    )


@dp.callback_query(F.data == "broadcast_send", AdminStates.broadcast_confirm)
async def broadcast_send(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer("🚫", show_alert=True)
    data = await state.get_data()
    text = data.get("broadcast_text", "")
    users = get_all_users()
    sent = 0
    for (uid,) in users:
        try:
            await safe_send_message(uid, text, parse_mode="HTML")
            sent += 1
        except Exception:
            pass
    save_broadcast(text, [], sent)
    await state.clear()
    await safe_edit_message(
        call.message,
        f"✅ Рассылка завершена!\n\n📨 Отправлено: <b>{sent}</b> из <b>{len(users)}</b>",
        parse_mode="HTML"
    )


# ══════════════════════════════════════════════
# 🚫 БАН / РАЗБАН
# ══════════════════════════════════════════════

@dp.callback_query(F.data == "admin_ban")
async def admin_ban_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer("🚫", show_alert=True)
    await state.set_state(AdminStates.ban_user_id)
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="❌ Отмена", callback_data="admin_panel"))
    await safe_edit_message(call.message, "🚫 Введите ID пользователя для бана:", reply_markup=kb.as_markup())


@dp.message(AdminStates.ban_user_id)
async def admin_ban_do(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if not message.text.lstrip('-').isdigit():
        await safe_send_message(message.chat.id, "❌ Введите корректный ID:")
        return
    uid = int(message.text)
    ban_user(uid)
    await state.clear()
    try:
        await safe_send_message(uid, "🚫 Вы заблокированы в этом боте.")
    except Exception:
        pass
    await safe_send_message(
        message.chat.id,
        f"✅ Пользователь <code>{uid}</code> заблокирован.", parse_mode="HTML"
    )


@dp.callback_query(F.data == "admin_unban")
async def admin_unban_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer("🚫", show_alert=True)
    await state.set_state(AdminStates.unban_user_id)
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="❌ Отмена", callback_data="admin_panel"))
    await safe_edit_message(call.message, "✅ Введите ID пользователя для разбана:", reply_markup=kb.as_markup())


@dp.message(AdminStates.unban_user_id)
async def admin_unban_do(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if not message.text.lstrip('-').isdigit():
        await safe_send_message(message.chat.id, "❌ Введите корректный ID:")
        return
    uid = int(message.text)
    unban_user(uid)
    await state.clear()
    await safe_send_message(
        message.chat.id,
        f"✅ Пользователь <code>{uid}</code> разблокирован.", parse_mode="HTML"
    )


# ══════════════════════════════════════════════
# 🔇 МУТ / РАЗМУТ
# ══════════════════════════════════════════════

@dp.callback_query(F.data == "admin_mute")
async def admin_mute_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer("🚫", show_alert=True)
    await state.set_state(AdminStates.mute_user_id)
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="❌ Отмена", callback_data="admin_panel"))
    await safe_edit_message(call.message, "🔇 Введите ID пользователя для мута:", reply_markup=kb.as_markup())


@dp.message(AdminStates.mute_user_id)
async def admin_mute_get_id(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if not message.text.lstrip('-').isdigit():
        await safe_send_message(message.chat.id, "❌ Введите корректный ID:")
        return
    await state.update_data(mute_uid=int(message.text))
    await state.set_state(AdminStates.mute_duration)
    await safe_send_message(message.chat.id, "⏱ Введите длительность мута в минутах:")


@dp.message(AdminStates.mute_duration)
async def admin_mute_do(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if not message.text.isdigit():
        await safe_send_message(message.chat.id, "❌ Введите число минут:")
        return
    data = await state.get_data()
    uid = data['mute_uid']
    minutes = int(message.text)
    mute_user(uid, minutes)
    await state.clear()
    await safe_send_message(
        message.chat.id,
        f"✅ Пользователь <code>{uid}</code> замучен на {minutes} мин.", parse_mode="HTML"
    )


@dp.callback_query(F.data == "admin_unmute")
async def admin_unmute_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer("🚫", show_alert=True)
    await state.set_state(AdminStates.unmute_user_id)
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="❌ Отмена", callback_data="admin_panel"))
    await safe_edit_message(call.message, "🔊 Введите ID пользователя для размута:", reply_markup=kb.as_markup())


@dp.message(AdminStates.unmute_user_id)
async def admin_unmute_do(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if not message.text.lstrip('-').isdigit():
        await safe_send_message(message.chat.id, "❌ Введите корректный ID:")
        return
    uid = int(message.text)
    unmute_user(uid)
    await state.clear()
    await safe_send_message(
        message.chat.id,
        f"✅ Пользователь <code>{uid}</code> размучен.", parse_mode="HTML"
    )


# ══════════════════════════════════════════════
# 📺 УПРАВЛЕНИЕ КАНАЛАМИ
# ══════════════════════════════════════════════

@dp.callback_query(F.data == "admin_channels")
async def admin_channels(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer("🚫", show_alert=True)
    channels = get_channels()
    text = "📺 <b>Подключённые каналы</b>\n\n"
    if channels:
        for c in channels:
            text += f"• {c['title']} (<code>{c['chan_id']}</code>)\n"
    else:
        text += "— каналов нет"
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="➕ Добавить канал", callback_data="admin_add_chan"))
    for c in channels:
        kb.row(InlineKeyboardButton(text=f"❌ Удалить {c['title']}", callback_data=f"admin_rm_chan_{c['id']}"))
    kb.row(InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel"))
    await safe_edit_message(call.message, text, reply_markup=kb.as_markup(), parse_mode="HTML")


@dp.callback_query(F.data == "admin_add_chan")
async def admin_add_chan_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer("🚫", show_alert=True)
    await state.set_state(AdminStates.add_chan_title)
    await safe_edit_message(call.message, "📺 Введите название канала:")


@dp.message(AdminStates.add_chan_title)
async def add_chan_title_handler(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.update_data(chan_title=message.text)
    await state.set_state(AdminStates.add_chan_url)
    await safe_send_message(message.chat.id, "🔗 Введите ссылку на канал (https://t.me/...):")


@dp.message(AdminStates.add_chan_url)
async def add_chan_url_handler(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.update_data(chan_url=message.text)
    await state.set_state(AdminStates.add_chan_id)
    await safe_send_message(message.chat.id, "🆔 Введите числовой ID канала (например: -1001234567890):")


@dp.message(AdminStates.add_chan_id)
async def add_chan_id_handler(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if not message.text.lstrip('-').isdigit():
        await safe_send_message(message.chat.id, "❌ Введите корректный ID канала:")
        return
    data = await state.get_data()
    add_channel(data['chan_title'], data['chan_url'], int(message.text))
    await state.clear()
    await safe_send_message(
        message.chat.id,
        f"✅ Канал <b>{data['chan_title']}</b> добавлен!", parse_mode="HTML"
    )


@dp.callback_query(F.data.startswith("admin_rm_chan_"))
async def admin_rm_chan(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer("🚫", show_alert=True)
    raw = call.data[len("admin_rm_chan_"):]
    if not raw.isdigit():
        return await call.answer("❌ Неверный ID", show_alert=True)
    remove_channel(int(raw))
    await call.answer("✅ Канал удалён!")
    await admin_channels(call, state)


# ══════════════════════════════════════════════
# 🔍 ПРОВЕРИТЬ ЮЗЕРА
# ══════════════════════════════════════════════

@dp.callback_query(F.data == "admin_check_user")
async def admin_check_user_start(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        return await call.answer("🚫", show_alert=True)
    await state.set_state(AdminStates.check_user_id)
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(text="❌ Отмена", callback_data="admin_panel"))
    await safe_edit_message(call.message, "🔍 Введите ID пользователя:", reply_markup=kb.as_markup())


@dp.message(AdminStates.check_user_id)
async def admin_check_user_do(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    if not message.text.lstrip('-').isdigit():
        await safe_send_message(message.chat.id, "❌ Введите корректный ID:")
        return
    uid = int(message.text)
    u = get_user(uid)
    await state.clear()
    if not u:
        await safe_send_message(
            message.chat.id,
            f"❌ Пользователь <code>{uid}</code> не найден.", parse_mode="HTML"
        )
        return
    muted = is_muted(uid)
    text = (
        f"👤 <b>Информация о пользователе</b>\n\n"
        f"🆔 ID: <code>{u['user_id']}</code>\n"
        f"🔖 Username: @{u['username'] or '—'}\n"
        f"📛 Имя: {u['full_name']}\n"
        f"📅 Регистрация: {u['joined_at'][:10]}\n"
        f"🚫 Бан: {'Да' if u['is_banned'] else 'Нет'}\n"
        f"🔇 Мут: {'Да' if muted else 'Нет'}\n"
        f"🔗 Рефералов: {u.get('ref_count', 0)}\n"
        f"💰 Реф. баланс: {u.get('ref_balance', 0.0):.2f} USDT\n"
    )
    if u.get("ref_by"):
        text += f"👥 Приглашён: <code>{u['ref_by']}</code>\n"
    await safe_send_message(message.chat.id, text, parse_mode="HTML")


# ══════════════════════════════════════════════
# 📦 ПОДКЛЮЧЕНИЕ КАТАЛОГА
# ══════════════════════════════════════════════

from catalog import register_catalog_handlers
register_catalog_handlers(dp, bot, ADMIN_IDS, safe_send_message, safe_edit_message)

# ══════════════════════════════════════════════
# 🛡️ ФИЛЬТР МУТА (должен быть последним)
# ══════════════════════════════════════════════

@dp.message()
async def message_filter(message: Message):
    if message.from_user and is_muted(message.from_user.id):
        await safe_send_message(message.chat.id, "🔇 Вы замучены и не можете отправлять сообщения.")

# ══════════════════════════════════════════════
# 🚀 ЗАПУСК
# ══════════════════════════════════════════════

async def main():
    print("🤖 Бот запущен!")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())

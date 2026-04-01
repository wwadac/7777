import asyncio
import logging
import sqlite3
import random
import io
from datetime import datetime
from typing import List, Dict, Optional

from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    CallbackQuery, Message, FSInputFile
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
import requests

from config import (
    CRYPTOBOT_TOKEN, CRYPTOBOT_API_URL, CRYPTOBOT_ASSET,
    PRODUCTS_PER_PAGE, SHUFFLE_PRODUCTS, STARS_PRICE_USD,
    ADMIN_STARS_USERNAME
)

# ══════════════════════════════════════════════
# 🔧 ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ══════════════════════════════════════════════

def usdt_to_stars(usdt_price: float) -> int:
    """Конвертирует USDT в Stars по рыночному курсу."""
    return round(usdt_price / STARS_PRICE_USD)

def mask_text(text: str) -> str:
    glyphs = {
        'а': 'α', 'в': 'β', 'е': '℮', 'и': 'u', 'к': 'k',
        'о': 'ο', 'п': 'π', 'р': 'ρ', 'с': 'c', 'т': 'm',
        'у': 'γ', 'А': 'Α', 'В': 'Β', 'Е': '℮', 'И': 'U',
        'К': 'K', 'О': 'Ο', 'П': 'Π', 'Р': 'Ρ', 'С': 'C',
        'Т': 'T', 'У': 'Υ'
    }
    return ''.join(glyphs.get(ch, ch) for ch in text)

# ══════════════════════════════════════════════
# 🎛️ FSM СОСТОЯНИЯ КАТАЛОГА
# ══════════════════════════════════════════════

class CatalogStates(StatesGroup):
    waiting_for_product_name        = State()
    waiting_for_product_price_crypto = State()
    waiting_for_product_description = State()
    waiting_for_screenshot          = State()
    waiting_for_crypto_payment      = State()
    waiting_for_txt_upload          = State()

# ══════════════════════════════════════════════
# 📊 БАЗА ДАННЫХ
# ══════════════════════════════════════════════

def init_catalog_db():
    conn = sqlite3.connect("bot_database.db")
    c = conn.cursor()
    # Таблица продуктов — только USDT-цена, stars считаются авто
    c.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL,
            price_usdt  REAL    NOT NULL,
            description TEXT,
            created_at  TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id                 INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id            INTEGER,
            product_id         INTEGER,
            payment_method     TEXT,
            amount             TEXT,
            status             TEXT,
            created_at         TEXT,
            completed_at       TEXT,
            crypto_invoice_id  TEXT,
            screenshot_file_id TEXT
        )
    """)
    conn.commit()
    conn.close()

def add_product(name: str, price_usdt: float, description: str = "") -> int:
    with sqlite3.connect("bot_database.db") as conn:
        cur = conn.execute(
            "INSERT INTO products (name, price_usdt, description, created_at) VALUES (?,?,?,?)",
            (name, price_usdt, description, datetime.now().isoformat())
        )
        return cur.lastrowid

def get_products(offset: int = 0, limit: int = PRODUCTS_PER_PAGE, shuffle: bool = False):
    with sqlite3.connect("bot_database.db") as conn:
        rows = conn.execute(
            "SELECT id, name, price_usdt, description FROM products ORDER BY id"
        ).fetchall()
    products = [
        {"id": r[0], "name": r[1], "price_usdt": r[2], "description": r[3]}
        for r in rows
    ]
    if shuffle:
        random.shuffle(products)
    return products[offset:offset + limit], len(products)

def get_product(product_id: int) -> Optional[dict]:
    with sqlite3.connect("bot_database.db") as conn:
        row = conn.execute(
            "SELECT id, name, price_usdt, description FROM products WHERE id=?",
            (product_id,)
        ).fetchone()
    if row:
        return {"id": row[0], "name": row[1], "price_usdt": row[2], "description": row[3]}
    return None

def delete_product_by_id(product_id: int):
    with sqlite3.connect("bot_database.db") as conn:
        conn.execute("DELETE FROM products WHERE id=?", (product_id,))

def clear_all_products():
    with sqlite3.connect("bot_database.db") as conn:
        conn.execute("DELETE FROM products")

def create_order(user_id, product_id, payment_method, amount, crypto_invoice_id=None) -> int:
    with sqlite3.connect("bot_database.db") as conn:
        cur = conn.execute(
            """INSERT INTO orders
               (user_id, product_id, payment_method, amount, status, created_at, crypto_invoice_id)
               VALUES (?,?,?,?,?,?,?)""",
            (user_id, product_id, payment_method, str(amount),
             'pending', datetime.now().isoformat(), crypto_invoice_id)
        )
        return cur.lastrowid

def update_order_status(order_id, status, completed_at=None, screenshot_file_id=None):
    with sqlite3.connect("bot_database.db") as conn:
        if completed_at:
            conn.execute(
                "UPDATE orders SET status=?, completed_at=?, screenshot_file_id=? WHERE id=?",
                (status, completed_at, screenshot_file_id, order_id)
            )
        else:
            conn.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))

def get_pending_order(user_id, product_id) -> Optional[int]:
    with sqlite3.connect("bot_database.db") as conn:
        row = conn.execute(
            "SELECT id FROM orders WHERE user_id=? AND product_id=? AND status='pending' ORDER BY id DESC LIMIT 1",
            (user_id, product_id)
        ).fetchone()
    return row[0] if row else None

# ══════════════════════════════════════════════
# 🤖 КРИПТОБОТ
# ══════════════════════════════════════════════

def create_crypto_invoice(amount: float) -> dict:
    headers = {'Crypto-Pay-API-Token': CRYPTOBOT_TOKEN}
    data = {'asset': CRYPTOBOT_ASSET, 'amount': f"{amount:.4f}"}
    response = requests.post(f"{CRYPTOBOT_API_URL}/createInvoice", headers=headers, json=data, timeout=15)
    result = response.json()
    if result.get('ok'):
        return result['result']
    raise Exception(f"CryptoBot error: {response.text}")

def check_crypto_invoice(invoice_id) -> Optional[dict]:
    headers = {'Crypto-Pay-API-Token': CRYPTOBOT_TOKEN}
    try:
        response = requests.get(
            f"{CRYPTOBOT_API_URL}/getInvoices",
            headers=headers,
            params={'invoice_ids': str(invoice_id)},
            timeout=15
        )
        if response.status_code == 200:
            items = response.json().get('result', {}).get('items', [])
            if items:
                return items[0]
    except Exception as e:
        logging.error(f"check_crypto_invoice error: {e}")
    return None

# ══════════════════════════════════════════════
# 🔧 РЕГИСТРАЦИЯ ХЭНДЛЕРОВ
# ══════════════════════════════════════════════

def register_catalog_handlers(dp: Dispatcher, bot: Bot, admin_ids: List[int], send_func, edit_func):
    init_catalog_db()

    # ─────────────────────────────────────────
    # 📦 КАТАЛОГ (просмотр)
    # ─────────────────────────────────────────

    async def _render_catalog_page(call: CallbackQuery, page: int):
        products, total = get_products(
            offset=page * PRODUCTS_PER_PAGE,
            shuffle=SHUFFLE_PRODUCTS
        )
        total_pages = max(1, (total + PRODUCTS_PER_PAGE - 1) // PRODUCTS_PER_PAGE)

        text = "📦 <b>К A T A Л О Г</b>\n\n"
        if not products:
            text += "❌ Товаров пока нет."

        kb = InlineKeyboardBuilder()
        for p in products:
            masked_name = mask_text(p['name'])
            stars = usdt_to_stars(p['price_usdt'])
            # Кнопка показывает и название, и цены
            btn_text = f"🛒 {masked_name}  |  {p['price_usdt']:.2f} USDT / {stars}⭐"
            kb.row(InlineKeyboardButton(
                text=btn_text,
                callback_data=f"product_{p['id']}"
            ))

        if total_pages > 1:
            nav = []
            if page > 0:
                nav.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"catalog_page_{page - 1}"))
            if page < total_pages - 1:
                nav.append(InlineKeyboardButton(text="Вперед ▶️", callback_data=f"catalog_page_{page + 1}"))
            if nav:
                kb.row(*nav)

        kb.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu"))
        await edit_func(call.message, text, reply_markup=kb.as_markup(), parse_mode="HTML")

    @dp.callback_query(F.data == "catalog")
    async def show_catalog(call: CallbackQuery, state: FSMContext):
        await state.clear()
        await _render_catalog_page(call, 0)

    @dp.callback_query(F.data.startswith("catalog_page_"))
    async def catalog_page(call: CallbackQuery, state: FSMContext):
        page = int(call.data.split("_")[2])
        await _render_catalog_page(call, page)

    # ─────────────────────────────────────────
    # 📄 КАРТОЧКА ТОВАРА
    # ─────────────────────────────────────────

    @dp.callback_query(F.data.startswith("product_"))
    async def product_detail(call: CallbackQuery, state: FSMContext):
        # Защита от конфликта с "product_" префиксами admin-коллбэков
        raw = call.data[len("product_"):]
        if not raw.isdigit():
            return
        product_id = int(raw)
        product = get_product(product_id)
        if not product:
            await call.answer("❌ Товар не найден", show_alert=True)
            return

        stars = usdt_to_stars(product['price_usdt'])
        text = (
            f"📦 <b>{product['name']}</b>\n\n"
            f"📝 <i>{product['description']}</i>\n\n"
            f"═══════════════════\n"
            f"💰 <b>Цена товара:</b>\n\n"
            f"   💎 <b>USDT:</b>  {product['price_usdt']:.2f} {CRYPTOBOT_ASSET}\n"
            f"   ⭐️ <b>Stars:</b> {stars} ⭐️\n"
            f"   <i>(1⭐ ≈ {STARS_PRICE_USD} USD)</i>\n\n"
            f"═══════════════════\n"
            f"👇 <b>Выберите способ оплаты:</b>"
        )

        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(
            text=f"💎 Оплатить {product['price_usdt']:.2f} USDT (CryptoBot)",
            callback_data=f"pay_crypto_{product_id}"
        ))
        kb.row(InlineKeyboardButton(
            text=f"⭐️ Оплатить {stars} Stars (Telegram)",
            callback_data=f"pay_stars_{product_id}"
        ))
        kb.row(InlineKeyboardButton(text="🔙 Назад в каталог", callback_data="catalog"))
        await edit_func(call.message, text, reply_markup=kb.as_markup(), parse_mode="HTML")
        await call.answer()

    # ─────────────────────────────────────────
    # ⭐ ОПЛАТА ЗВЁЗДАМИ
    # ─────────────────────────────────────────

    @dp.callback_query(F.data.startswith("pay_stars_"))
    async def pay_stars(call: CallbackQuery, state: FSMContext):
        raw = call.data[len("pay_stars_"):]
        if not raw.isdigit():
            return
        product_id = int(raw)
        product = get_product(product_id)
        if not product:
            await call.answer("❌ Товар не найден", show_alert=True)
            return

        existing = get_pending_order(call.from_user.id, product_id)
        if existing:
            await call.answer("⚠️ У вас уже есть незавершённый заказ на этот товар.", show_alert=True)
            return

        stars = usdt_to_stars(product['price_usdt'])
        order_id = create_order(call.from_user.id, product_id, 'stars', stars)
        await state.update_data(order_id=order_id, product=product, stars=stars)
        await state.set_state(CatalogStates.waiting_for_screenshot)

        text = (
            f"⭐️ <b>Оплата звёздами Telegram</b>\n\n"
            f"📦 Товар:  <b>{product['name']}</b>\n"
            f"💰 Цена:   <b>{product['price_usdt']:.2f} USDT</b>\n"
            f"⭐️ К оплате: <b>{stars} Stars</b>\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 <b>Инструкция:</b>\n"
            f"1️⃣ Перейдите к администратору: @{ADMIN_STARS_USERNAME}\n"
            f"2️⃣ Переведите <b>{stars} Stars</b> на этот аккаунт\n"
            f"3️⃣ Нажмите кнопку <b>«✅ Отправить скриншот»</b> и пришлите скриншот\n\n"
            f"👨‍💻 Администратор проверит и выдаст товар"
        )

        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="🚀 Перейти к администратору", url=f"https://t.me/{ADMIN_STARS_USERNAME}"))
        kb.row(InlineKeyboardButton(text="✅ Отправить скриншот", callback_data="send_screenshot_ready"))
        kb.row(InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_order"))
        await edit_func(call.message, text, reply_markup=kb.as_markup(), parse_mode="HTML")
        await call.answer()

    # ─────────────────────────────────────────
    # 💎 ОПЛАТА USDT (CryptoBot)
    # ─────────────────────────────────────────

    @dp.callback_query(F.data.startswith("pay_crypto_"))
    async def pay_crypto(call: CallbackQuery, state: FSMContext):
        raw = call.data[len("pay_crypto_"):]
        if not raw.isdigit():
            return
        product_id = int(raw)
        product = get_product(product_id)
        if not product:
            await call.answer("❌ Товар не найден", show_alert=True)
            return

        try:
            invoice = create_crypto_invoice(product['price_usdt'])
        except Exception as e:
            logging.error(f"CryptoBot invoice error: {e}")
            await edit_func(call.message, f"❌ Ошибка при создании счёта:\n{e}\n\nПопробуйте позже.", reply_markup=None)
            return

        stars = usdt_to_stars(product['price_usdt'])
        order_id = create_order(
            call.from_user.id, product_id, 'crypto',
            product['price_usdt'], crypto_invoice_id=invoice['invoice_id']
        )

        text = (
            f"💎 <b>Оплата {CRYPTOBOT_ASSET} через CryptoBot</b>\n\n"
            f"📦 Товар:  <b>{product['name']}</b>\n"
            f"💰 Цена:   <b>{product['price_usdt']:.2f} USDT</b>\n"
            f"⭐️ Эквивалент: {stars} Stars\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"1️⃣ Нажмите кнопку оплаты\n"
            f"2️⃣ Переведите <b>{product['price_usdt']:.2f} {CRYPTOBOT_ASSET}</b>\n"
            f"3️⃣ После оплаты нажмите <b>«✅ Проверить оплату»</b>"
        )

        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(
            text=f"💎 Оплатить {product['price_usdt']:.2f} {CRYPTOBOT_ASSET}",
            url=invoice['pay_url']
        ))
        kb.row(InlineKeyboardButton(text="✅ Проверить оплату", callback_data=f"check_crypto_{order_id}"))
        kb.row(InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_order"))
        await edit_func(call.message, text, reply_markup=kb.as_markup(), parse_mode="HTML")
        await call.answer()

    @dp.callback_query(F.data.startswith("check_crypto_"))
    async def check_crypto_payment(call: CallbackQuery, state: FSMContext):
        raw = call.data[len("check_crypto_"):]
        if not raw.isdigit():
            return
        order_id = int(raw)

        with sqlite3.connect("bot_database.db") as conn:
            row = conn.execute(
                "SELECT crypto_invoice_id, user_id, product_id FROM orders WHERE id=?",
                (order_id,)
            ).fetchone()
        if not row:
            await call.answer("❌ Заказ не найден", show_alert=True)
            return

        crypto_invoice_id, user_id, product_id = row
        invoice = check_crypto_invoice(crypto_invoice_id)

        if invoice and invoice.get('status') == 'paid':
            update_order_status(order_id, 'completed', completed_at=datetime.now().isoformat())
            product = get_product(product_id)
            await edit_func(
                call.message,
                f"✅ <b>Оплата подтверждена!</b>\n\n"
                f"📦 Товар: <b>{product['name']}</b>\n"
                f"💰 Оплачено: {product['price_usdt']:.2f} {CRYPTOBOT_ASSET}\n"
                f"🔢 Заказ №{order_id}\n\n"
                f"Спасибо за покупку! 🎉",
                reply_markup=None, parse_mode="HTML"
            )
        else:
            await call.answer("⏳ Оплата ещё не получена. Попробуйте через несколько секунд.", show_alert=True)

    # ─────────────────────────────────────────
    # 📸 СКРИНШОТ (Stars-оплата)
    # ─────────────────────────────────────────

    @dp.callback_query(F.data == "send_screenshot_ready")
    async def screenshot_ready(call: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        if not data.get('order_id'):
            await call.answer("❌ Заказ не найден. Начните заново.", show_alert=True)
            return
        await send_func(call.from_user.id, "📸 Отправьте скриншот перевода Stars:")
        await state.set_state(CatalogStates.waiting_for_screenshot)
        await call.answer()

    @dp.message(CatalogStates.waiting_for_screenshot)
    async def receive_screenshot(message: Message, state: FSMContext):
        data = await state.get_data()
        if not data or not data.get('order_id'):
            await send_func(message.chat.id, "❌ Заказ не найден. Начните заново.")
            await state.clear()
            return

        if not message.photo:
            await send_func(message.chat.id, "❌ Пожалуйста, отправьте скриншот (фото).")
            return

        order_id = data['order_id']
        product  = data['product']
        stars    = data.get('stars', usdt_to_stars(product['price_usdt']))

        file_id = message.photo[-1].file_id
        update_order_status(order_id, 'pending', screenshot_file_id=file_id)

        caption = (
            f"🛍 <b>НОВЫЙ ЗАКАЗ НА ПРОВЕРКУ</b>\n\n"
            f"👤 Пользователь: {message.from_user.full_name}\n"
            f"🔖 Username: @{message.from_user.username or '—'}\n"
            f"🆔 ID: <code>{message.from_user.id}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📦 Товар: <b>{product['name']}</b>\n"
            f"💳 Способ: ⭐️ Stars\n"
            f"💰 Цена USDT: {product['price_usdt']:.2f} USDT\n"
            f"⭐️ Сумма Stars: <b>{stars} Stars</b>\n"
            f"🔢 Заказ №{order_id}\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ Подтвердить заказ?"
        )

        kb = InlineKeyboardBuilder()
        kb.row(
            InlineKeyboardButton(text="✅ ПОДТВЕРДИТЬ", callback_data=f"verify_order_{order_id}"),
            InlineKeyboardButton(text="❌ ОТКЛОНИТЬ",  callback_data=f"reject_order_{order_id}")
        )

        for admin_id in admin_ids:
            try:
                await bot.send_photo(
                    admin_id, photo=file_id,
                    caption=caption, reply_markup=kb.as_markup(), parse_mode="HTML"
                )
            except Exception as e:
                logging.error(f"Не удалось отправить фото админу {admin_id}: {e}")

        await send_func(
            message.chat.id,
            "✅ <b>Скриншот отправлен на проверку!</b>\n\nОжидайте подтверждения администратора.",
            parse_mode="HTML"
        )
        await state.clear()

    @dp.callback_query(F.data.startswith("verify_order_"))
    async def verify_order(call: CallbackQuery, state: FSMContext):
        if call.from_user.id not in admin_ids:
            return await call.answer("🚫 Нет доступа", show_alert=True)
        order_id = int(call.data.split("_")[2])
        update_order_status(order_id, 'completed', completed_at=datetime.now().isoformat())

        with sqlite3.connect("bot_database.db") as conn:
            row = conn.execute(
                "SELECT user_id, product_id FROM orders WHERE id=?", (order_id,)
            ).fetchone()

        if row:
            user_id, product_id = row
            product = get_product(product_id)
            name = product['name'] if product else "—"
            await send_func(
                user_id,
                f"✅ <b>ЗАКАЗ ПОДТВЕРЖДЁН!</b>\n\n"
                f"📦 Товар: <b>{name}</b>\n"
                f"🔢 Заказ №{order_id}\n\n"
                f"Спасибо за покупку! 🎉",
                parse_mode="HTML"
            )

        await edit_func(call.message, f"✅ Заказ №{order_id} подтверждён.", reply_markup=None)
        await call.answer("✅ Заказ подтверждён!")

    @dp.callback_query(F.data.startswith("reject_order_"))
    async def reject_order(call: CallbackQuery, state: FSMContext):
        if call.from_user.id not in admin_ids:
            return await call.answer("🚫 Нет доступа", show_alert=True)
        order_id = int(call.data.split("_")[2])
        update_order_status(order_id, 'failed')

        with sqlite3.connect("bot_database.db") as conn:
            row = conn.execute(
                "SELECT user_id FROM orders WHERE id=?", (order_id,)
            ).fetchone()

        if row:
            await send_func(
                row[0],
                f"❌ <b>Заказ №{order_id} отклонён</b>\n\n"
                f"Пожалуйста, свяжитесь с поддержкой для уточнения деталей.",
                parse_mode="HTML"
            )

        await edit_func(call.message, f"❌ Заказ №{order_id} отклонён.", reply_markup=None)
        await call.answer("❌ Заказ отклонён")

    @dp.callback_query(F.data == "cancel_order")
    async def cancel_order_handler(call: CallbackQuery, state: FSMContext):
        await state.clear()
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="📦 Каталог", callback_data="catalog"))
        kb.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu"))
        await edit_func(call.message, "❌ Заказ отменён.", reply_markup=kb.as_markup())
        await call.answer("Заказ отменён")

    # ══════════════════════════════════════════════
    # 👑 АДМИНИСТРИРОВАНИЕ КАТАЛОГА
    # ══════════════════════════════════════════════

    @dp.callback_query(F.data == "admin_manage_catalog")
    async def admin_manage_catalog(call: CallbackQuery, state: FSMContext):
        if call.from_user.id not in admin_ids:
            return await call.answer("🚫 Нет доступа", show_alert=True)
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="➕ Добавить товар",    callback_data="admin_add_product"))
        kb.row(InlineKeyboardButton(text="📋 Список товаров",    callback_data="admin_list_products"))
        kb.row(InlineKeyboardButton(text="📤 Загрузить из TXT",  callback_data="admin_upload_txt"))
        kb.row(InlineKeyboardButton(text="🗑 Очистить каталог",  callback_data="admin_clear_catalog"))
        kb.row(InlineKeyboardButton(text="🔙 Назад",             callback_data="admin_panel"))
        await edit_func(
            call.message, "📦 <b>Управление каталогом</b>",
            reply_markup=kb.as_markup(), parse_mode="HTML"
        )

    # ── Добавить товар вручную ──

    @dp.callback_query(F.data == "admin_add_product")
    async def add_product_start(call: CallbackQuery, state: FSMContext):
        if call.from_user.id not in admin_ids:
            return await call.answer("🚫 Нет доступа", show_alert=True)
        await state.set_state(CatalogStates.waiting_for_product_name)
        await edit_func(call.message, "📝 Введите <b>название товара</b>:", parse_mode="HTML")
        await call.answer()

    @dp.message(CatalogStates.waiting_for_product_name)
    async def get_product_name(message: Message, state: FSMContext):
        if message.from_user.id not in admin_ids:
            return
        await state.update_data(name=message.text.strip())
        await state.set_state(CatalogStates.waiting_for_product_price_crypto)
        await send_func(
            message.chat.id,
            f"💰 Введите <b>цену в {CRYPTOBOT_ASSET}</b> (например: 4.50)\n"
            f"⭐️ Stars будут рассчитаны автоматически по курсу {STARS_PRICE_USD} USD/звезда.",
            parse_mode="HTML"
        )

    @dp.message(CatalogStates.waiting_for_product_price_crypto)
    async def get_price_crypto(message: Message, state: FSMContext):
        if message.from_user.id not in admin_ids:
            return
        try:
            price = float(message.text.strip().replace(',', '.'))
            if price <= 0:
                raise ValueError
        except ValueError:
            await send_func(message.chat.id, "❌ Введите положительное число (например: 4.50):")
            return
        stars = usdt_to_stars(price)
        await state.update_data(price_usdt=price)
        await state.set_state(CatalogStates.waiting_for_product_description)
        await send_func(
            message.chat.id,
            f"✅ Цена: <b>{price:.2f} USDT = {stars} Stars</b>\n\n"
            f"📝 Теперь введите <b>описание товара</b>:",
            parse_mode="HTML"
        )

    @dp.message(CatalogStates.waiting_for_product_description)
    async def get_description(message: Message, state: FSMContext):
        if message.from_user.id not in admin_ids:
            return
        data = await state.get_data()
        product_id = add_product(
            name=data['name'],
            price_usdt=data['price_usdt'],
            description=message.text.strip()
        )
        stars = usdt_to_stars(data['price_usdt'])
        await state.clear()
        await send_func(
            message.chat.id,
            f"✅ <b>Товар добавлен!</b>\n\n"
            f"📦 {data['name']}\n"
            f"💰 {data['price_usdt']:.2f} USDT / {stars} Stars\n"
            f"🆔 ID: {product_id}",
            parse_mode="HTML"
        )
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="📦 Каталог", callback_data="catalog"))
        kb.row(InlineKeyboardButton(text="⚙️ Управление каталогом", callback_data="admin_manage_catalog"))
        await send_func(message.chat.id, "Что дальше?", reply_markup=kb.as_markup())

    # ── Загрузка из TXT ──

    @dp.callback_query(F.data == "admin_upload_txt")
    async def upload_txt_start(call: CallbackQuery, state: FSMContext):
        if call.from_user.id not in admin_ids:
            return await call.answer("🚫 Нет доступа", show_alert=True)
        await state.set_state(CatalogStates.waiting_for_txt_upload)
        await edit_func(
            call.message,
            "📤 <b>Загрузка товаров из TXT</b>\n\n"
            "<b>Формат файла (3 строки на товар):</b>\n"
            "<code>Название товара\n"
            "5.50\n"
            "Описание товара\n"
            "---\n"
            "Название 2\n"
            "2.00\n"
            "Описание 2</code>\n\n"
            "📌 Разделитель товаров: <code>---</code>\n"
            "📌 Цена — в USDT, Stars рассчитаются автоматически\n\n"
            "<b>Отправьте TXT файл:</b>",
            parse_mode="HTML"
        )
        await call.answer()

    @dp.message(CatalogStates.waiting_for_txt_upload)
    async def process_txt_file(message: Message, state: FSMContext):
        if message.from_user.id not in admin_ids:
            return

        if not message.document:
            await send_func(message.chat.id, "❌ Отправьте файл в формате TXT.")
            return

        try:
            file = await bot.get_file(message.document.file_id)
            file_content = await bot.download_file(file.file_path)
            text = file_content.read().decode('utf-8')
        except Exception as e:
            await send_func(message.chat.id, f"❌ Не удалось прочитать файл: {e}")
            await state.clear()
            return

        # Парсим блоки через разделитель ---
        raw_blocks = [b.strip() for b in text.split('---') if b.strip()]

        success = 0
        errors = []

        for idx, block in enumerate(raw_blocks, 1):
            lines = [l.strip() for l in block.split('\n') if l.strip()]
            if len(lines) < 3:
                errors.append(f"Товар {idx}: нужно минимум 3 строки (название, цена, описание)")
                continue

            name = lines[0]
            price_str = lines[1].replace(',', '.')
            description = '\n'.join(lines[2:])

            try:
                price = float(price_str)
                if price <= 0:
                    raise ValueError("Цена должна быть > 0")
            except ValueError as e:
                errors.append(f"Товар {idx} ({name}): неверная цена '{price_str}' — {e}")
                continue

            add_product(name, price, description)
            success += 1

        result = f"✅ <b>Загрузка завершена!</b>\n\n📦 Добавлено: <b>{success}</b>\n❌ Ошибок: <b>{len(errors)}</b>"
        if errors:
            result += "\n\n⚠️ <b>Ошибки:</b>\n" + "\n".join(errors[:10])

        await send_func(message.chat.id, result, parse_mode="HTML")
        await state.clear()

        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="📦 Управление каталогом", callback_data="admin_manage_catalog"))
        await send_func(message.chat.id, "Перейти к управлению?", reply_markup=kb.as_markup())

    # ── Список товаров ──

    @dp.callback_query(F.data == "admin_list_products")
    async def list_products(call: CallbackQuery, state: FSMContext):
        if call.from_user.id not in admin_ids:
            return await call.answer("🚫 Нет доступа", show_alert=True)
        products, _ = get_products(offset=0, limit=1000, shuffle=False)
        if not products:
            kb = InlineKeyboardBuilder()
            kb.row(InlineKeyboardButton(text="🔙 Назад", callback_data="admin_manage_catalog"))
            await edit_func(call.message, "📭 <b>Каталог пуст</b>", reply_markup=kb.as_markup(), parse_mode="HTML")
            return

        text = "📋 <b>Список товаров</b>\n\n"
        for p in products:
            stars = usdt_to_stars(p['price_usdt'])
            text += f"🆔 <b>{p['id']}</b> • {p['name']}\n   💰 {p['price_usdt']:.2f} USDT / ⭐️ {stars} Stars\n\n"

        kb = InlineKeyboardBuilder()
        for p in products:
            kb.row(InlineKeyboardButton(
                text=f"❌ Удалить: {p['name']}",
                callback_data=f"admin_del_product_{p['id']}"
            ))
        kb.row(InlineKeyboardButton(text="🔙 Назад", callback_data="admin_manage_catalog"))
        await edit_func(call.message, text, reply_markup=kb.as_markup(), parse_mode="HTML")

    @dp.callback_query(F.data.startswith("admin_del_product_"))
    async def delete_product_handler(call: CallbackQuery, state: FSMContext):
        if call.from_user.id not in admin_ids:
            return await call.answer("🚫 Нет доступа", show_alert=True)
        raw = call.data[len("admin_del_product_"):]
        if not raw.isdigit():
            return await call.answer("❌ Неверный ID", show_alert=True)
        delete_product_by_id(int(raw))
        await call.answer("✅ Товар удалён!")
        await list_products(call, state)

    # ── Очистить каталог ──

    @dp.callback_query(F.data == "admin_clear_catalog")
    async def clear_catalog(call: CallbackQuery, state: FSMContext):
        if call.from_user.id not in admin_ids:
            return await call.answer("🚫 Нет доступа", show_alert=True)
        clear_all_products()
        await call.answer("✅ Весь каталог очищен!", show_alert=True)
        await admin_manage_catalog(call, state)

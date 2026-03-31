import asyncio
import logging
import sqlite3
import json
import requests
from datetime import datetime
from typing import List, Dict, Optional

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ══════════════════════════════════════════════
# ⚙️ КОНФИГУРАЦИЯ КРИПТОБОТА
# ══════════════════════════════════════════════

CRYPTOBOT_TOKEN = "554603:AAoJCtxFiCgxpUiQAWVNUi6bF4q7zbcThyy"   # Замените на свой токен
CRYPTOBOT_API_URL = "https://pay.crypt.bot/api"

PRODUCTS_PER_PAGE = 10

# ══════════════════════════════════════════════
# 🎛️ FSM СОСТОЯНИЯ КАТАЛОГА
# ══════════════════════════════════════════════

class CatalogStates(StatesGroup):
    waiting_for_product_name = State()
    waiting_for_product_price_stars = State()
    waiting_for_product_price_crypto = State()
    waiting_for_product_description = State()
    waiting_for_screenshot = State()
    waiting_for_crypto_payment = State()

# ══════════════════════════════════════════════
# 📊 БАЗА ДАННЫХ
# ══════════════════════════════════════════════

def init_catalog_db():
    conn = sqlite3.connect("bot_database.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price_stars INTEGER,
            price_crypto REAL,
            description TEXT,
            created_at TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            product_id INTEGER,
            payment_method TEXT,
            amount TEXT,
            status TEXT,
            created_at TEXT,
            completed_at TEXT,
            crypto_invoice_id TEXT,
            screenshot_file_id TEXT
        )
    """)
    conn.commit()
    conn.close()

def add_product(name, price_stars=None, price_crypto=None, description=""):
    with sqlite3.connect("bot_database.db") as conn:
        cur = conn.execute(
            "INSERT INTO products (name, price_stars, price_crypto, description, created_at) VALUES (?,?,?,?,?)",
            (name, price_stars, price_crypto, description, datetime.now().isoformat())
        )
        return cur.lastrowid

def get_products(offset=0, limit=PRODUCTS_PER_PAGE):
    with sqlite3.connect("bot_database.db") as conn:
        rows = conn.execute(
            "SELECT id, name, price_stars, price_crypto, description FROM products ORDER BY id LIMIT ? OFFSET ?",
            (limit, offset)
        ).fetchall()
        return [{"id": r[0], "name": r[1], "price_stars": r[2], "price_crypto": r[3], "description": r[4]} for r in rows]

def get_product(product_id):
    with sqlite3.connect("bot_database.db") as conn:
        row = conn.execute(
            "SELECT id, name, price_stars, price_crypto, description FROM products WHERE id=?",
            (product_id,)
        ).fetchone()
        if row:
            return {"id": row[0], "name": row[1], "price_stars": row[2], "price_crypto": row[3], "description": row[4]}
    return None

def get_total_products():
    with sqlite3.connect("bot_database.db") as conn:
        return conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]

def delete_product(product_id):
    with sqlite3.connect("bot_database.db") as conn:
        conn.execute("DELETE FROM products WHERE id=?", (product_id,))

def create_order(user_id, product_id, payment_method, amount, crypto_invoice_id=None):
    with sqlite3.connect("bot_database.db") as conn:
        cur = conn.execute(
            "INSERT INTO orders (user_id, product_id, payment_method, amount, status, created_at, crypto_invoice_id) VALUES (?,?,?,?,?,?,?)",
            (user_id, product_id, payment_method, amount, 'pending', datetime.now().isoformat(), crypto_invoice_id)
        )
        return cur.lastrowid

def update_order_status(order_id, status, completed_at=None, screenshot_file_id=None):
    with sqlite3.connect("bot_database.db") as conn:
        if completed_at:
            conn.execute("UPDATE orders SET status=?, completed_at=?, screenshot_file_id=? WHERE id=?",
                         (status, completed_at, screenshot_file_id, order_id))
        else:
            conn.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))

def get_pending_order(user_id, product_id):
    with sqlite3.connect("bot_database.db") as conn:
        row = conn.execute(
            "SELECT id FROM orders WHERE user_id=? AND product_id=? AND status='pending' ORDER BY id DESC LIMIT 1",
            (user_id, product_id)
        ).fetchone()
        return row[0] if row else None

# ══════════════════════════════════════════════
# 🤖 ФУНКЦИИ КРИПТОБОТА
# ══════════════════════════════════════════════

def create_crypto_invoice(amount, currency='USDT'):
    headers = {'Crypto-Pay-API-Token': CRYPTOBOT_TOKEN}
    data = {'amount': amount, 'currency': currency}
    response = requests.post(f"{CRYPTOBOT_API_URL}/createInvoice", headers=headers, data=data)
    if response.status_code == 200:
        return response.json()['result']
    else:
        raise Exception(f"Cryptobot error: {response.text}")

def check_crypto_invoice(invoice_id):
    headers = {'Crypto-Pay-API-Token': CRYPTOBOT_TOKEN}
    response = requests.get(f"{CRYPTOBOT_API_URL}/getInvoices", headers=headers, params={'invoice_ids': invoice_id})
    if response.status_code == 200:
        invoices = response.json()['result']['items']
        if invoices:
            return invoices[0]
    return None

# ══════════════════════════════════════════════
# 🔧 РЕГИСТРАЦИЯ ХЭНДЛЕРОВ
# ══════════════════════════════════════════════

def register_catalog_handlers(dp: Dispatcher, bot: Bot, admin_ids: List[int], send_func, edit_func):
    init_catalog_db()

    # --- Каталог для пользователей ---
    @dp.callback_query(F.data == "catalog")
    async def show_catalog(call: CallbackQuery, state: FSMContext):
        await state.clear()
        page = 0
        products = get_products(offset=page * PRODUCTS_PER_PAGE)
        total = get_total_products()
        total_pages = (total + PRODUCTS_PER_PAGE - 1) // PRODUCTS_PER_PAGE

        text = "📦 <b>Каталог товаров</b>\n\n"
        if not products:
            text += "Товаров пока нет."
        else:
            for p in products:
                text += f"• <b>{p['name']}</b>\n"
                if p['price_stars']:
                    text += f"  ⭐️ {p['price_stars']} звезд\n"
                if p['price_crypto']:
                    text += f"  💰 {p['price_crypto']} USDT\n"
                text += f"  🔍 <i>{p['description'][:50]}...</i>\n\n"

        kb = InlineKeyboardBuilder()
        for p in products:
            kb.row(InlineKeyboardButton(text=p['name'], callback_data=f"product_{p['id']}"))

        if total_pages > 1:
            nav = []
            if page > 0:
                nav.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"catalog_page_{page-1}"))
            if page < total_pages - 1:
                nav.append(InlineKeyboardButton(text="➡️ Вперед", callback_data=f"catalog_page_{page+1}"))
            kb.row(*nav)

        kb.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu"))
        await edit_func(call.message, text, reply_markup=kb.as_markup(), parse_mode="HTML")

    @dp.callback_query(F.data.startswith("catalog_page_"))
    async def catalog_page(call: CallbackQuery, state: FSMContext):
        page = int(call.data.split("_")[2])
        products = get_products(offset=page * PRODUCTS_PER_PAGE)
        total = get_total_products()
        total_pages = (total + PRODUCTS_PER_PAGE - 1) // PRODUCTS_PER_PAGE

        text = "📦 <b>Каталог товаров</b>\n\n"
        for p in products:
            text += f"• <b>{p['name']}</b>\n"
            if p['price_stars']:
                text += f"  ⭐️ {p['price_stars']} звезд\n"
            if p['price_crypto']:
                text += f"  💰 {p['price_crypto']} USDT\n"
            text += f"  🔍 <i>{p['description'][:50]}...</i>\n\n"

        kb = InlineKeyboardBuilder()
        for p in products:
            kb.row(InlineKeyboardButton(text=p['name'], callback_data=f"product_{p['id']}"))

        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"catalog_page_{page-1}"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton(text="➡️ Вперед", callback_data=f"catalog_page_{page+1}"))
        if nav:
            kb.row(*nav)

        kb.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu"))
        await edit_func(call.message, text, reply_markup=kb.as_markup(), parse_mode="HTML")

    @dp.callback_query(F.data.startswith("product_"))
    async def product_detail(call: CallbackQuery, state: FSMContext):
        product_id = int(call.data.split("_")[1])
        product = get_product(product_id)
        if not product:
            await call.answer("Товар не найден", show_alert=True)
            return

        text = f"📦 <b>{product['name']}</b>\n\n{product['description']}\n\n"
        text += f"⭐️ Звезды: {product['price_stars'] if product['price_stars'] else '—'}\n"
        text += f"💰 USDT: {product['price_crypto'] if product['price_crypto'] else '—'}\n\n"
        text += "Выберите способ оплаты:"

        kb = InlineKeyboardBuilder()
        if product['price_stars']:
            kb.row(InlineKeyboardButton(text="⭐️ Оплатить звездами", callback_data=f"pay_stars_{product_id}"))
        if product['price_crypto']:
            kb.row(InlineKeyboardButton(text="💰 Оплатить через Cryptobot", callback_data=f"pay_crypto_{product_id}"))
        kb.row(InlineKeyboardButton(text="🔙 Назад в каталог", callback_data="catalog"))
        await edit_func(call.message, text, reply_markup=kb.as_markup(), parse_mode="HTML")

    # --- Оплата звёздами (ручная проверка) ---
    @dp.callback_query(F.data.startswith("pay_stars_"))
    async def pay_stars(call: CallbackQuery, state: FSMContext):
        product_id = int(call.data.split("_")[2])
        product = get_product(product_id)
        if not product:
            await call.answer("Товар не найден", show_alert=True)
            return

        existing = get_pending_order(call.from_user.id, product_id)
        if existing:
            await call.answer("У вас уже есть незавершенный заказ на этот товар.", show_alert=True)
            return

        amount = str(product['price_stars'])
        order_id = create_order(call.from_user.id, product_id, 'stars', amount)

        await state.update_data(order_id=order_id, product=product)
        await state.set_state(CatalogStates.waiting_for_screenshot)

        admin_stars_username = "admin_stars_username"  # Укажите здесь ваш ник для приёма звёзд
        text = (f"⭐️ <b>Оплата звездами</b>\n\n"
                f"Товар: {product['name']}\n"
                f"Сумма: {amount} звезд\n\n"
                f"Для оплаты переведите звезды на аккаунт:\n"
                f"<code>{admin_stars_username}</code>\n\n"
                f"После перевода отправьте сюда скриншот подтверждения.\n"
                f"Администратор проверит и подтвердит заказ.")
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="❌ Отменить заказ", callback_data="cancel_order"))
        await edit_func(call.message, text, reply_markup=kb.as_markup(), parse_mode="HTML")
        await call.answer()

    @dp.message(CatalogStates.waiting_for_screenshot)
    async def receive_screenshot(message: Message, state: FSMContext):
        data = await state.get_data()
        order_id = data['order_id']
        product = data['product']

        if not message.photo:
            await send_func(message.chat.id, "Пожалуйста, отправьте скриншот оплаты.")
            return

        photo = message.photo[-1]
        file_id = photo.file_id

        update_order_status(order_id, 'pending', screenshot_file_id=file_id)

        caption = (f"📦 <b>Новый заказ на проверку</b>\n\n"
                   f"Пользователь: {message.from_user.full_name} (@{message.from_user.username})\n"
                   f"ID: {message.from_user.id}\n"
                   f"Товар: {product['name']}\n"
                   f"Способ: звезды\n"
                   f"Сумма: {product['price_stars']} звезд\n"
                   f"Заказ №{order_id}\n\n"
                   f"Подтвердить?")
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"verify_order_{order_id}"),
               InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_order_{order_id}"))

        for admin_id in admin_ids:
            try:
                await bot.send_photo(admin_id, photo, caption=caption, reply_markup=kb.as_markup(), parse_mode="HTML")
            except Exception as e:
                logging.error(f"Не удалось отправить админу {admin_id}: {e}")

        await send_func(message.chat.id, "✅ Скриншот отправлен на проверку. Ожидайте подтверждения.")
        await state.clear()

    @dp.callback_query(F.data.startswith("verify_order_"))
    async def verify_order(call: CallbackQuery, state: FSMContext):
        order_id = int(call.data.split("_")[2])
        update_order_status(order_id, 'completed', completed_at=datetime.now().isoformat())
        with sqlite3.connect("bot_database.db") as conn:
            row = conn.execute("SELECT user_id, product_id FROM orders WHERE id=?", (order_id,)).fetchone()
        if row:
            user_id, product_id = row
            product = get_product(product_id)
            await send_func(user_id, f"✅ Ваш заказ №{order_id} на товар «{product['name']}» подтвержден!")
        await edit_func(call.message, f"Заказ №{order_id} подтвержден.", reply_markup=None)
        await call.answer()

    @dp.callback_query(F.data.startswith("reject_order_"))
    async def reject_order(call: CallbackQuery, state: FSMContext):
        order_id = int(call.data.split("_")[2])
        update_order_status(order_id, 'failed')
        with sqlite3.connect("bot_database.db") as conn:
            row = conn.execute("SELECT user_id, product_id FROM orders WHERE id=?", (order_id,)).fetchone()
        if row:
            user_id, product_id = row
            await send_func(user_id, f"❌ Ваш заказ №{order_id} был отклонен администратором. Пожалуйста, свяжитесь с поддержкой.")
        await edit_func(call.message, f"Заказ №{order_id} отклонен.", reply_markup=None)
        await call.answer()

    # --- Оплата через Cryptobot ---
    @dp.callback_query(F.data.startswith("pay_crypto_"))
    async def pay_crypto(call: CallbackQuery, state: FSMContext):
        product_id = int(call.data.split("_")[2])
        product = get_product(product_id)
        if not product:
            await call.answer("Товар не найден", show_alert=True)
            return

        try:
            invoice = create_crypto_invoice(product['price_crypto'])
        except Exception as e:
            await edit_func(call.message, f"❌ Ошибка при создании счета: {e}\nПопробуйте позже.")
            return

        amount = str(product['price_crypto'])
        order_id = create_order(call.from_user.id, product_id, 'crypto', amount, crypto_invoice_id=invoice['invoice_id'])

        text = (f"💰 <b>Оплата через Cryptobot</b>\n\n"
                f"Товар: {product['name']}\n"
                f"Сумма: {product['price_crypto']} USDT\n\n"
                f"Оплатите по ссылке:\n{invoice['pay_url']}\n\n"
                f"После оплаты нажмите кнопку «Проверить оплату».")
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="✅ Проверить оплату", callback_data=f"check_crypto_{order_id}"))
        kb.row(InlineKeyboardButton(text="❌ Отменить заказ", callback_data="cancel_order"))
        await edit_func(call.message, text, reply_markup=kb.as_markup(), parse_mode="HTML")
        await call.answer()

    @dp.callback_query(F.data.startswith("check_crypto_"))
    async def check_crypto_payment(call: CallbackQuery, state: FSMContext):
        order_id = int(call.data.split("_")[2])
        with sqlite3.connect("bot_database.db") as conn:
            row = conn.execute("SELECT crypto_invoice_id, user_id, product_id FROM orders WHERE id=?", (order_id,)).fetchone()
        if not row:
            await call.answer("Заказ не найден", show_alert=True)
            return
        crypto_invoice_id, user_id, product_id = row

        invoice = check_crypto_invoice(crypto_invoice_id)
        if invoice and invoice['status'] == 'paid':
            update_order_status(order_id, 'completed', completed_at=datetime.now().isoformat())
            product = get_product(product_id)
            await edit_func(call.message, f"✅ Оплата получена! Заказ №{order_id} на товар «{product['name']}» выполнен.")
            await send_func(user_id, f"✅ Ваш заказ №{order_id} на товар «{product['name']}» подтвержден!")
        else:
            await call.answer("Оплата еще не получена. Попробуйте позже.", show_alert=True)

    @dp.callback_query(F.data == "cancel_order")
    async def cancel_order(call: CallbackQuery, state: FSMContext):
        await state.clear()
        await edit_func(call.message, "Заказ отменен.")
        await call.answer()

    # --- Администрирование каталога ---
    @dp.callback_query(F.data == "admin_manage_catalog")
    async def admin_manage_catalog(call: CallbackQuery, state: FSMContext):
        if call.from_user.id not in admin_ids:
            return await call.answer("Нет доступа", show_alert=True)
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="➕ Добавить товар", callback_data="admin_add_product"))
        kb.row(InlineKeyboardButton(text="📋 Список товаров", callback_data="admin_list_products"))
        kb.row(InlineKeyboardButton(text="🔙 Назад", callback_data="admin_panel"))
        await edit_func(call.message, "Управление каталогом", reply_markup=kb.as_markup())

    @dp.callback_query(F.data == "admin_add_product")
    async def add_product_start(call: CallbackQuery, state: FSMContext):
        await state.set_state(CatalogStates.waiting_for_product_name)
        await edit_func(call.message, "Введите название товара:")
        await call.answer()

    @dp.message(CatalogStates.waiting_for_product_name)
    async def get_product_name(message: Message, state: FSMContext):
        await state.update_data(name=message.text)
        await state.set_state(CatalogStates.waiting_for_product_price_stars)
        await send_func(message.chat.id, "Введите цену в звездах (или 0, если не используется):")

    @dp.message(CatalogStates.waiting_for_product_price_stars)
    async def get_price_stars(message: Message, state: FSMContext):
        if not message.text.isdigit():
            await send_func(message.chat.id, "Введите число:")
            return
        await state.update_data(price_stars=int(message.text))
        await state.set_state(CatalogStates.waiting_for_product_price_crypto)
        await send_func(message.chat.id, "Введите цену в USDT (или 0, если не используется):")

    @dp.message(CatalogStates.waiting_for_product_price_crypto)
    async def get_price_crypto(message: Message, state: FSMContext):
        try:
            price = float(message.text)
        except ValueError:
            await send_func(message.chat.id, "Введите число (можно дробное):")
            return
        await state.update_data(price_crypto=price)
        await state.set_state(CatalogStates.waiting_for_product_description)
        await send_func(message.chat.id, "Введите описание товара:")

    @dp.message(CatalogStates.waiting_for_product_description)
    async def get_description(message: Message, state: FSMContext):
        data = await state.get_data()
        product_id = add_product(
            name=data['name'],
            price_stars=data['price_stars'] if data['price_stars'] != 0 else None,
            price_crypto=data['price_crypto'] if data['price_crypto'] != 0 else None,
            description=message.text
        )
        await state.clear()
        await send_func(message.chat.id, f"✅ Товар «{data['name']}» добавлен (ID: {product_id})")
        kb = InlineKeyboardBuilder()
        kb.row(InlineKeyboardButton(text="📦 Каталог", callback_data="catalog"))
        kb.row(InlineKeyboardButton(text="⚙️ Админ панель", callback_data="admin_panel"))
        await send_func(message.chat.id, "Что дальше?", reply_markup=kb.as_markup())

    @dp.callback_query(F.data == "admin_list_products")
    async def list_products(call: CallbackQuery, state: FSMContext):
        products = get_products(offset=0, limit=100)
        if not products:
            await edit_func(call.message, "Нет товаров.")
            return
        text = "📋 <b>Список товаров</b>\n\n"
        for p in products:
            text += f"ID {p['id']}: {p['name']} — ⭐️{p['price_stars'] if p['price_stars'] else '—'} | 💰{p['price_crypto'] if p['price_crypto'] else '—'}\n"
        kb = InlineKeyboardBuilder()
        for p in products:
            kb.row(InlineKeyboardButton(text=f"❌ Удалить {p['name']}", callback_data=f"admin_del_product_{p['id']}"))
        kb.row(InlineKeyboardButton(text="🔙 Назад", callback_data="admin_manage_catalog"))
        await edit_func(call.message, text, reply_markup=kb.as_markup(), parse_mode="HTML")

    @dp.callback_query(F.data.startswith("admin_del_product_"))
    async def delete_product(call: CallbackQuery, state: FSMContext):
        product_id = int(call.data.split("_")[3])
        delete_product(product_id)
        await call.answer("Товар удален")
        await admin_manage_catalog(call, state)

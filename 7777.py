import asyncio
import random
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# === ВСТАВЬ СВОЙ ТОКЕН ===
BOT_TOKEN = "8534057742:AAE1EDuHUmBXo0vxsXR5XorlWgeXe3-4L98"

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Пары похожих эмодзи (основной и похожий на него)
EMOJI_PAIRS = [
    ("😀", "😃"), ("😊", "☺️"), ("🙂", "🙃"), ("😄", "😁"),
    ("🔴", "🟠"), ("🟢", "🟡"), ("🔵", "🟣"), ("⚫", "🟤"),
    ("🍎", "🍏"), ("🍊", "🍑"), ("🍋", "🍌"), ("🍇", "🫐"),
    ("🐶", "🐕"), ("🐱", "🐈"), ("🐭", "🐹"), ("🐰", "🐇"),
    ("❤️", "🧡"), ("💛", "💚"), ("💙", "💜"), ("🖤", "🤍"),
    ("⭐", "🌟"), ("✨", "💫"), ("🌙", "🌛"), ("☀️", "🌞"),
    ("🏠", "🏡"), ("🚗", "🚙"), ("✈️", "🛩️"), ("⚽", "🏀"),
    ("🎵", "🎶"), ("🔔", "🔕"), ("💎", "💠"), ("🎈", "🎀"),
    ("🌸", "🌺"), ("🌹", "🌷"), ("🌻", "🌼"), ("🍀", "☘️"),
    ("👀", "👁️"), ("👋", "🤚"), ("👍", "👎"), ("✌️", "🤞"),
    ("🦊", "🐺"), ("🦁", "🐯"), ("🐻", "🐨"), ("🐼", "🐻‍❄️"),
    ("🍕", "🍔"), ("🍟", "🌭"), ("🍩", "🍪"), ("🍰", "🎂"),
]

class GameState(StatesGroup):
    playing = State()

# Хранение данных игроков
players_data = {}

def get_player_data(user_id):
    if user_id not in players_data:
        players_data[user_id] = {
            "score": 0,
            "high_score": 0,
            "level": 1,
            "streak": 0,
            "games_played": 0
        }
    return players_data[user_id]

def get_grid_size(level):
    """Размер сетки зависит от уровня"""
    if level <= 2:
        return 5, 5  # 25 эмодзи
    elif level <= 4:
        return 6, 5  # 30 эмодзи
    elif level <= 6:
        return 6, 6  # 36 эмодзи
    elif level <= 8:
        return 7, 6  # 42 эмодзи
    elif level <= 10:
        return 7, 7  # 49 эмодзи
    else:
        return 8, 7  # 56 эмодзи

def get_odd_count(level):
    """Количество лишних эмодзи"""
    if level <= 3:
        return 1
    elif level <= 6:
        return random.randint(1, 2)
    elif level <= 10:
        return random.randint(1, 3)
    else:
        return random.randint(2, 4)

def generate_game(level):
    """Генерация игрового поля"""
    rows, cols = get_grid_size(level)
    total = rows * cols
    odd_count = get_odd_count(level)
    
    # Выбираем пару эмодзи
    main_emoji, odd_emoji = random.choice(EMOJI_PAIRS)
    
    # Иногда меняем местами (чтобы было разнообразнее)
    if random.random() > 0.5:
        main_emoji, odd_emoji = odd_emoji, main_emoji
    
    # Создаём поле
    grid = [main_emoji] * total
    
    # Размещаем лишние эмодзи
    odd_positions = random.sample(range(total), odd_count)
    for pos in odd_positions:
        grid[pos] = odd_emoji
    
    return {
        "grid": grid,
        "rows": rows,
        "cols": cols,
        "main_emoji": main_emoji,
        "odd_emoji": odd_emoji,
        "odd_positions": odd_positions,
        "odd_count": odd_count
    }

def format_grid(game_data):
    """Форматирование поля для отображения"""
    grid = game_data["grid"]
    rows = game_data["rows"]
    cols = game_data["cols"]
    
    # Добавляем нумерацию колонок
    header = "    " + "  ".join([f"{i+1}️⃣" for i in range(cols)])
    
    lines = [header, ""]
    
    row_labels = ["🅰️", "🅱️", "©️", "Ⓜ️", "🅾️", "🅿️", "🆎", "🆑"]
    
    for r in range(rows):
        row_emoji = grid[r * cols:(r + 1) * cols]
        # Добавляем пробелы между эмодзи для лучшей видимости
        row_str = row_labels[r] + "  " + "  ".join(row_emoji)
        lines.append(row_str)
    
    return "\n".join(lines)

def format_grid_simple(game_data):
    """Упрощённое форматирование без нумерации - БОЛЬШОЕ ПОЛЕ"""
    grid = game_data["grid"]
    rows = game_data["rows"]
    cols = game_data["cols"]
    
    lines = []
    for r in range(rows):
        row_emoji = grid[r * cols:(r + 1) * cols]
        # Большие пробелы для объёмности
        row_str = " ".join(row_emoji)
        lines.append(row_str)
        lines.append("")  # Пустая строка между рядами
    
    return "\n".join(lines)

def create_answer_keyboard(game_data):
    """Создание клавиатуры для ответа"""
    rows = game_data["rows"]
    cols = game_data["cols"]
    
    buttons = []
    row_labels = ["A", "B", "C", "D", "E", "F", "G", "H"]
    
    for r in range(rows):
        row_buttons = []
        for c in range(cols):
            position = r * cols + c
            label = f"{row_labels[r]}{c+1}"
            row_buttons.append(
                InlineKeyboardButton(
                    text=label,
                    callback_data=f"answer_{position}"
                )
            )
        buttons.append(row_buttons)
    
    # Кнопка сдаться
    buttons.append([
        InlineKeyboardButton(text="🏳️ Сдаться", callback_data="give_up"),
        InlineKeyboardButton(text="❓ Подсказка", callback_data="hint")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def create_simple_keyboard(game_data):
    """Упрощённая клавиатура - выбор номера"""
    total = game_data["rows"] * game_data["cols"]
    
    buttons = []
    current_row = []
    
    for i in range(total):
        current_row.append(
            InlineKeyboardButton(
                text=str(i + 1),
                callback_data=f"answer_{i}"
            )
        )
        if len(current_row) == 7:  # 7 кнопок в ряд
            buttons.append(current_row)
            current_row = []
    
    if current_row:
        buttons.append(current_row)
    
    buttons.append([
        InlineKeyboardButton(text="🏳️ Сдаться", callback_data="give_up"),
        InlineKeyboardButton(text="❓ Подсказка", callback_data="hint")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    player = get_player_data(message.from_user.id)
    
    text = f"""
🎮 **НАЙДИ ЛИШНИЙ ЭМОДЗИ** 🎮

Привет, {message.from_user.first_name}! 👋

📋 **Правила игры:**
• Тебе показывается поле с эмодзи
• Один или несколько эмодзи отличаются от других
• Найди их и нажми на правильную позицию!

📊 **Твоя статистика:**
• Рекорд: {player['high_score']} 🏆
• Игр сыграно: {player['games_played']} 🎲

🎯 **Уровни сложности:**
• Чем выше уровень - тем больше поле
• Больше лишних эмодзи на высоких уровнях
• Эмодзи становятся более похожими!

Нажми /play чтобы начать игру!
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Начать игру", callback_data="new_game")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton(text="❓ Помощь", callback_data="help")]
    ])
    
    await message.answer(text, parse_mode="Markdown", reply_markup=keyboard)

@dp.message(Command("play"))
async def cmd_play(message: types.Message, state: FSMContext):
    await start_new_game(message.from_user.id, message, state)

async def start_new_game(user_id, message_or_callback, state: FSMContext, edit=False):
    player = get_player_data(user_id)
    game_data = generate_game(player["level"])
    
    await state.update_data(game=game_data, hints_used=0)
    await state.set_state(GameState.playing)
    
    # Формируем поле с номерами
    grid = game_data["grid"]
    rows = game_data["rows"]
    cols = game_data["cols"]
    
    # Создаём красивое поле с номерами
    field_lines = []
    field_lines.append("```")
    
    # Заголовок
    header = "     "
    for c in range(cols):
        header += f" {c+1:2} "
    field_lines.append(header)
    field_lines.append("    " + "────" * cols)
    
    for r in range(rows):
        line = f" {r+1:2} │"
        for c in range(cols):
            idx = r * cols + c
            num = idx + 1
            line += f" {grid[idx]} "
        field_lines.append(line)
    
    field_lines.append("```")
    
    field_text = "\n".join(field_lines)
    
    # Альтернативный простой вариант
    simple_field = []
    num = 1
    for r in range(rows):
        row_line = ""
        for c in range(cols):
            idx = r * cols + c
            row_line += f"{grid[idx]} "
        simple_field.append(row_line)
        simple_field.append(f"{'   '.join([str(r*cols+c+1) for c in range(cols)])}")
        simple_field.append("")
    
    # Ещё более простой вариант - просто большое поле
    big_field = []
    for r in range(rows):
        row_emojis = []
        for c in range(cols):
            idx = r * cols + c
            row_emojis.append(grid[idx])
        big_field.append("  ".join(row_emojis))
    
    big_field_text = "\n\n".join(big_field)
    
    odd_word = "лишний эмодзи" if game_data["odd_count"] == 1 else f"лишних эмодзи: {game_data['odd_count']}"
    
    text = f"""
🎮 **УРОВЕНЬ {player['level']}** | 💰 Очки: {player['score']} | 🔥 Серия: {player['streak']}

{'═' * 20}

{big_field_text}

{'═' * 20}

🔍 Найди {odd_word}!
📏 Поле: {rows}x{cols} ({rows*cols} эмодзи)

👆 Выбери номер позиции (считай слева направо, сверху вниз):
"""
    
    keyboard = create_simple_keyboard(game_data)
    
    if edit and hasattr(message_or_callback, 'message'):
        await message_or_callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
    else:
        if hasattr(message_or_callback, 'answer'):
            await message_or_callback.answer(text, parse_mode="Markdown", reply_markup=keyboard)
        else:
            await message_or_callback.message.answer(text, parse_mode="Markdown", reply_markup=keyboard)

@dp.callback_query(F.data == "new_game")
async def callback_new_game(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await start_new_game(callback.from_user.id, callback, state, edit=True)

@dp.callback_query(F.data.startswith("answer_"))
async def callback_answer(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    
    if "game" not in data:
        await callback.answer("Игра не найдена! Начни новую.", show_alert=True)
        return
    
    game_data = data["game"]
    position = int(callback.data.split("_")[1])
    player = get_player_data(callback.from_user.id)
    
    if position in game_data["odd_positions"]:
        # Правильный ответ!
        points = 10 * player["level"]
        player["score"] += points
        player["streak"] += 1
        player["games_played"] += 1
        
        # Повышаем уровень каждые 3 правильных ответа
        if player["streak"] % 3 == 0:
            player["level"] = min(player["level"] + 1, 15)
        
        if player["score"] > player["high_score"]:
            player["high_score"] = player["score"]
        
        # Показываем где были лишние
        grid_copy = game_data["grid"].copy()
        for pos in game_data["odd_positions"]:
            grid_copy[pos] = "✅"
        
        text = f"""
🎉 **ПРАВИЛЬНО!** 🎉

✅ Ты нашёл лишний эмодзи!

Лишний эмодзи: {game_data['odd_emoji']}
Основной эмодзи: {game_data['main_emoji']}

💰 +{points} очков!
📊 Всего: {player['score']} очков
🔥 Серия: {player['streak']} подряд!
📈 Уровень: {player['level']}

{'🆙 Уровень повышен!' if player['streak'] % 3 == 0 else ''}
"""
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="▶️ Следующий раунд", callback_data="new_game")],
            [InlineKeyboardButton(text="📊 Статистика", callback_data="stats")],
            [InlineKeyboardButton(text="🏠 Меню", callback_data="menu")]
        ])
        
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
        await state.clear()
        
    else:
        # Неправильный ответ
        player["streak"] = 0
        player["level"] = max(1, player["level"] - 1)
        player["games_played"] += 1
        
        # Показываем правильный ответ
        grid = game_data["grid"]
        rows = game_data["rows"]
        cols = game_data["cols"]
        
        # Формируем поле с отмеченными позициями
        marked_grid = []
        for r in range(rows):
            row_emojis = []
            for c in range(cols):
                idx = r * cols + c
                if idx in game_data["odd_positions"]:
                    row_emojis.append("🔴")  # Отмечаем лишние
                elif idx == position:
                    row_emojis.append("❌")  # Что выбрал игрок
                else:
                    row_emojis.append(grid[idx])
            marked_grid.append("  ".join(row_emojis))
        
        marked_text = "\n\n".join(marked_grid)
        
        text = f"""
😢 **НЕПРАВИЛЬНО!**

{marked_text}

🔴 = лишний эмодзи (правильный ответ)
❌ = твой выбор

Лишний был: {game_data['odd_emoji']}
Основной был: {game_data['main_emoji']}

📊 Очки: {player['score']}
🔥 Серия сброшена
📉 Уровень: {player['level']}
"""
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Попробовать снова", callback_data="new_game")],
            [InlineKeyboardButton(text="🏠 Меню", callback_data="menu")]
        ])
        
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
        await state.clear()
    
    await callback.answer()

@dp.callback_query(F.data == "hint")
async def callback_hint(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    
    if "game" not in data:
        await callback.answer("Игра не найдена!", show_alert=True)
        return
    
    game_data = data["game"]
    hints_used = data.get("hints_used", 0)
    
    if hints_used >= 2:
        await callback.answer("Больше подсказок нет! 🙈", show_alert=True)
        return
    
    # Даём подсказку
    odd_pos = game_data["odd_positions"][0]
    rows = game_data["rows"]
    cols = game_data["cols"]
    
    row_num = odd_pos // cols + 1
    col_num = odd_pos % cols + 1
    
    if hints_used == 0:
        hint_text = f"Подсказка: лишний эмодзи в строке {row_num}"
    else:
        hint_text = f"Подсказка: лишний эмодзи в строке {row_num}, столбце {col_num}"
    
    await state.update_data(hints_used=hints_used + 1)
    await callback.answer(hint_text, show_alert=True)

@dp.callback_query(F.data == "give_up")
async def callback_give_up(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    
    if "game" not in data:
        await callback.answer("Игра не найдена!", show_alert=True)
        return
    
    game_data = data["game"]
    player = get_player_data(callback.from_user.id)
    player["streak"] = 0
    
    # Показываем где были лишние
    grid = game_data["grid"]
    rows = game_data["rows"]
    cols = game_data["cols"]
    
    marked_grid = []
    for r in range(rows):
        row_emojis = []
        for c in range(cols):
            idx = r * cols + c
            if idx in game_data["odd_positions"]:
                row_emojis.append("🔴")
            else:
                row_emojis.append(grid[idx])
        marked_grid.append("  ".join(row_emojis))
    
    marked_text = "\n\n".join(marked_grid)
    
    text = f"""
🏳️ **ТЫ СДАЛСЯ**

{marked_text}

🔴 = лишний эмодзи

Лишний был: {game_data['odd_emoji']}
Основной был: {game_data['main_emoji']}
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Новая игра", callback_data="new_game")],
        [InlineKeyboardButton(text="🏠 Меню", callback_data="menu")]
    ])
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
    await state.clear()
    await callback.answer()

@dp.callback_query(F.data == "stats")
async def callback_stats(callback: types.CallbackQuery):
    player = get_player_data(callback.from_user.id)
    
    text = f"""
📊 **ТВОЯ СТАТИСТИКА**

👤 Игрок: {callback.from_user.first_name}

🏆 Рекорд: {player['high_score']} очков
💰 Текущие очки: {player['score']}
📈 Уровень: {player['level']}
🔥 Текущая серия: {player['streak']}
🎲 Игр сыграно: {player['games_played']}
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Играть", callback_data="new_game")],
        [InlineKeyboardButton(text="🔄 Сбросить прогресс", callback_data="reset")],
        [InlineKeyboardButton(text="🏠 Меню", callback_data="menu")]
    ])
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data == "reset")
async def callback_reset(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if user_id in players_data:
        players_data[user_id] = {
            "score": 0,
            "high_score": 0,
            "level": 1,
            "streak": 0,
            "games_played": 0
        }
    
    await callback.answer("Прогресс сброшен! 🔄", show_alert=True)
    await callback_stats(callback)

@dp.callback_query(F.data == "menu")
async def callback_menu(callback: types.CallbackQuery):
    player = get_player_data(callback.from_user.id)
    
    text = f"""
🎮 **НАЙДИ ЛИШНИЙ ЭМОДЗИ** 🎮

📊 **Твоя статистика:**
• Рекорд: {player['high_score']} 🏆
• Уровень: {player['level']} 📈
• Игр сыграно: {player['games_played']} 🎲

Выбери действие:
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Начать игру", callback_data="new_game")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton(text="❓ Помощь", callback_data="help")]
    ])
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data == "help")
async def callback_help(callback: types.CallbackQuery):
    text = """
❓ **ПОМОЩЬ**

🎯 **Цель игры:**
Найти лишний эмодзи, который отличается от остальных.

📋 **Как играть:**
1️⃣ Смотришь на поле с эмодзи
2️⃣ Ищешь тот, который отличается
3️⃣ Нажимаешь на его номер

📈 **Уровни:**
• Уровень растёт каждые 3 правильных ответа
• Чем выше уровень - тем больше поле
• На высоких уровнях может быть несколько лишних!

💡 **Подсказки:**
• Доступно 2 подсказки за раунд
• Первая показывает строку
• Вторая показывает столбец

🏆 **Очки:**
• 10 × уровень за правильный ответ
• Серия сбрасывается при ошибке
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Играть", callback_data="new_game")],
        [InlineKeyboardButton(text="🏠 Меню", callback_data="menu")]
    ])
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
    await callback.answer()

async def main():
    print("🎮 Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

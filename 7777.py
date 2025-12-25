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

# ========================================
# ОГРОМНАЯ БАЗА ПОХОЖИХ ЭМОДЗИ
# ========================================

# Уровень 1-3: Легко различимые
EASY_PAIRS = [
    ("😀", "😢"), ("🔴", "🔵"), ("🍎", "🍌"), ("🐶", "🐱"),
    ("❤️", "💚"), ("⭐", "🌙"), ("🌞", "🌧️"), ("🎈", "🎁"),
    ("🚗", "✈️"), ("⚽", "🎸"), ("🏠", "🏢"), ("🌳", "🌊"),
    ("🍕", "🍦"), ("📱", "💻"), ("🎮", "📚"), ("👟", "👒"),
    ("🦁", "🐘"), ("🌹", "🌵"), ("🍔", "🍣"), ("☀️", "❄️"),
]

# Уровень 4-6: Средняя сложность
MEDIUM_PAIRS = [
    ("😀", "😃"), ("😊", "🙂"), ("😄", "😁"), ("🤗", "😊"),
    ("🔴", "🟠"), ("🟢", "🟡"), ("🔵", "🟣"), ("⚫", "🟤"),
    ("🍎", "🍏"), ("🍊", "🍑"), ("🍋", "🍌"), ("🍇", "🫐"),
    ("🐶", "🐕"), ("🐱", "🐈"), ("🐭", "🐹"), ("🐰", "🐇"),
    ("❤️", "🧡"), ("💛", "💚"), ("💙", "💜"), ("🖤", "🤍"),
    ("⭐", "🌟"), ("✨", "💫"), ("🌙", "🌛"), ("☀️", "🌞"),
    ("🏠", "🏡"), ("🚗", "🚙"), ("✈️", "🛩️"), ("⚽", "🏀"),
    ("🌸", "🌺"), ("🌹", "🌷"), ("🌻", "🌼"), ("🍀", "☘️"),
    ("🦊", "🐺"), ("🦁", "🐯"), ("🐻", "🐨"), ("🐼", "🐻‍❄️"),
    ("🍕", "🍔"), ("🍟", "🌭"), ("🍩", "🍪"), ("🍰", "🎂"),
    ("👀", "👁️"), ("👋", "🤚"), ("👍", "👎"), ("✌️", "🤞"),
]

# Уровень 7-10: Сложно
HARD_PAIRS = [
    # Очень похожие лица
    ("😀", "😃"), ("😃", "😄"), ("😄", "😁"), ("😁", "😆"),
    ("🙂", "🙃"), ("😊", "☺️"), ("🥲", "😊"), ("😇", "🙂"),
    ("😐", "😑"), ("😶", "😐"), ("🫤", "😐"), ("😏", "😌"),
    ("🤔", "🤨"), ("🧐", "🤔"), ("😒", "😏"), ("🙄", "😒"),
    ("😔", "😞"), ("😟", "😕"), ("🙁", "☹️"), ("😢", "😥"),
    ("😰", "😨"), ("😱", "😨"), ("😳", "🥺"), ("😬", "😅"),
    
    # Похожие сердца
    ("❤️", "♥️"), ("🧡", "🔶"), ("💛", "⭐"), ("💚", "🟢"),
    ("💙", "🔵"), ("💜", "🟣"), ("🤍", "⚪"), ("🖤", "⚫"),
    ("💗", "💖"), ("💓", "💕"), ("💘", "💝"), ("❣️", "💔"),
    
    # Похожие круги и формы
    ("🔴", "🟠"), ("🟠", "🟡"), ("🟡", "🟢"), ("🟢", "🔵"),
    ("🔵", "🟣"), ("🟣", "🟤"), ("⚪", "⚫"), ("🔘", "⚪"),
    ("⭕", "🔴"), ("🔺", "🔻"), ("🔷", "🔹"), ("🔶", "🔸"),
    
    # Похожие животные
    ("🐕", "🐶"), ("🐩", "🐕"), ("🦮", "🐕‍🦺"), ("🐕", "🐺"),
    ("🐈", "🐱"), ("🐈‍⬛", "🐈"), ("🐆", "🐅"), ("🦁", "🐯"),
    ("🐻", "🐻‍❄️"), ("🐨", "🐻"), ("🐼", "🐻"), ("🦝", "🐼"),
    ("🐵", "🙈"), ("🙉", "🙊"), ("🐒", "🐵"), ("🦍", "🦧"),
    ("🐔", "🐓"), ("🐤", "🐥"), ("🐣", "🐤"), ("🦆", "🦢"),
    ("🐸", "🐢"), ("🦎", "🐊"), ("🐍", "🐉"), ("🦕", "🦖"),
    
    # Похожие фрукты/еда
    ("🍎", "🍏"), ("🍑", "🍊"), ("🍋", "🍋‍🟩"), ("🥭", "🍑"),
    ("🍇", "🫐"), ("🍓", "🍒"), ("🍒", "🍎"), ("🥝", "🥒"),
    ("🍔", "🍕"), ("🌭", "🍖"), ("🥓", "🥩"), ("🍗", "🍖"),
    ("🍜", "🍝"), ("🍛", "🍲"), ("🥘", "🍳"), ("🧇", "🥞"),
    
    # Похожие символы
    ("✓", "✔️"), ("✕", "✖️"), ("➕", "✚"), ("➖", "−"),
    ("⬆️", "↑"), ("⬇️", "↓"), ("⬅️", "←"), ("➡️", "→"),
]

# Уровень 11-15: ОЧЕНЬ СЛОЖНО - минимальные отличия!
EXTREME_PAIRS = [
    # Почти идентичные эмодзи
    ("😀", "😃"), ("😃", "😺"), ("🙂", "🙃"),
    ("👁️", "👀"), ("👁", "👁️"), 
    ("🌕", "🌝"), ("🌑", "🌚"), ("🌙", "🌛"), ("🌜", "🌛"),
    ("⭐", "🌟"), ("✨", "💫"), ("⚡", "🌟"),
    ("❤️", "♥️"), ("💙", "🩵"), ("💚", "🩶"),
    ("🔴", "⭕"), ("🔵", "🫧"), ("⚫", "🖤"), ("⚪", "🤍"),
    ("🟠", "🔶"), ("🟡", "💛"), ("🟢", "💚"), ("🟣", "💜"),
    ("➡️", "▶️"), ("⬅️", "◀️"), ("⬆️", "🔼"), ("⬇️", "🔽"),
    ("☀️", "🌞"), ("🌤️", "⛅"), ("🌥️", "☁️"),
    ("💧", "💦"), ("🌊", "🌀"),
    ("🎵", "🎶"), ("🔔", "🔕"), ("🔊", "🔉"),
    ("📱", "📲"), ("💻", "🖥️"), ("⌨️", "🖲️"),
    ("📄", "📃"), ("📋", "📄"), ("📁", "📂"),
    ("🔒", "🔓"), ("🔐", "🔏"),
    ("⏰", "⏱️"), ("⏱️", "⏲️"), ("🕐", "🕑"),
    ("🔍", "🔎"), ("💡", "🔆"),
    
    # Флаги (очень похожие)
    ("🇫🇷", "🇳🇱"), ("🇷🇺", "🇳🇱"), ("🇮🇹", "🇮🇪"),
    ("🇧🇪", "🇩🇪"), ("🇦🇹", "🇱🇻"), ("🇮🇩", "🇲🇨"),
    ("🇷🇴", "🇹🇩"), ("🇳🇬", "🇮🇳"),
    
    # Руки (похожие жесты)
    ("👋", "🤚"), ("✋", "🖐️"), ("🖖", "✋"),
    ("👍", "👍🏻"), ("👎", "👎🏻"), ("👊", "✊"),
    ("🤜", "🤛"), ("👏", "🙌"), ("🤲", "👐"),
    ("🤝", "🙏"), ("✌️", "🤞"), ("🤟", "🤘"),
    ("👌", "🤌"), ("🤏", "👌"), ("👈", "👉"),
    
    # Часы (разное время)
    ("🕐", "🕑"), ("🕒", "🕓"), ("🕔", "🕕"),
    ("🕖", "🕗"), ("🕘", "🕙"), ("🕚", "🕛"),
    ("🕜", "🕝"), ("🕞", "🕟"), ("🕠", "🕡"),
    
    # Луны
    ("🌑", "🌒"), ("🌒", "🌓"), ("🌓", "🌔"),
    ("🌔", "🌕"), ("🌕", "🌖"), ("🌖", "🌗"),
    ("🌗", "🌘"), ("🌘", "🌑"),
    
    # Погода
    ("☀️", "🌤️"), ("🌤️", "⛅"), ("⛅", "🌥️"),
    ("🌥️", "☁️"), ("🌦️", "🌧️"), ("🌧️", "⛈️"),
    ("🌨️", "🌩️"), ("🌪️", "🌫️"),
    
    # Цветы
    ("🌸", "🌺"), ("🌺", "🌹"), ("🌹", "🥀"),
    ("🌷", "🌹"), ("🌻", "🌼"), ("💮", "🏵️"),
    ("🌾", "🌿"), ("☘️", "🍀"), ("🍃", "🌿"),
]

# Уровень 16-20: НЕВОЗМОЖНО (для хардкорщиков)
INSANE_PAIRS = [
    # Вариации скинтонов
    ("👍", "👍🏻"), ("👍🏻", "👍🏼"), ("👍🏼", "👍🏽"),
    ("👍🏽", "👍🏾"), ("👍🏾", "👍🏿"),
    ("👋", "👋🏻"), ("👋🏻", "👋🏼"), ("👋🏼", "👋🏽"),
    ("✋", "✋🏻"), ("✋🏻", "✋🏼"), ("✋🏼", "✋🏽"),
    ("👏", "👏🏻"), ("👏🏻", "👏🏼"), ("👏🏼", "👏🏽"),
    
    # Мужские/женские вариации
    ("👨", "👩"), ("👦", "👧"), ("🧔", "🧔‍♀️"),
    ("👱", "👱‍♀️"), ("🧓", "👴"), ("👴", "👵"),
    ("🙍", "🙍‍♂️"), ("🙎", "🙎‍♂️"), ("💁", "💁‍♂️"),
    ("🙋", "🙋‍♂️"), ("🧏", "🧏‍♂️"), ("🙇", "🙇‍♂️"),
    
    # Ультра-похожие символы
    ("一", "ー"), ("О", "O"), ("А", "A"),
    ("│", "┃"), ("─", "━"), ("┌", "╭"),
]

class GameState(StatesGroup):
    playing = State()

players_data = {}

def get_player_data(user_id):
    if user_id not in players_data:
        players_data[user_id] = {
            "score": 0,
            "high_score": 0,
            "level": 1,
            "streak": 0,
            "games_played": 0,
            "perfect_games": 0
        }
    return players_data[user_id]

def get_emoji_pairs_for_level(level):
    """Выбор пар эмодзи в зависимости от уровня"""
    if level <= 3:
        return EASY_PAIRS
    elif level <= 6:
        return EASY_PAIRS + MEDIUM_PAIRS
    elif level <= 10:
        return MEDIUM_PAIRS + HARD_PAIRS
    elif level <= 15:
        return HARD_PAIRS + EXTREME_PAIRS
    else:
        return EXTREME_PAIRS + INSANE_PAIRS

def get_grid_size(level):
    """Размер сетки - максимум 8 кнопок в ряд (ограничение Telegram)"""
    if level <= 2:
        return 4, 4   # 16 эмодзи
    elif level <= 4:
        return 5, 4   # 20 эмодзи
    elif level <= 6:
        return 5, 5   # 25 эмодзи
    elif level <= 8:
        return 6, 5   # 30 эмодзи
    elif level <= 10:
        return 6, 6   # 36 эмодзи
    elif level <= 12:
        return 7, 6   # 42 эмодзи
    elif level <= 15:
        return 7, 7   # 49 эмодзи
    elif level <= 18:
        return 8, 7   # 56 эмодзи
    else:
        return 8, 8   # 64 эмодзи (максимум!)

def get_odd_count(level):
    """Количество лишних эмодзи"""
    if level <= 5:
        return 1
    elif level <= 10:
        return random.randint(1, 2)
    elif level <= 15:
        return random.randint(1, 3)
    else:
        return random.randint(2, 4)

def generate_game(level):
    """Генерация игрового поля"""
    cols, rows = get_grid_size(level)
    total = rows * cols
    odd_count = get_odd_count(level)
    
    pairs = get_emoji_pairs_for_level(level)
    main_emoji, odd_emoji = random.choice(pairs)
    
    if random.random() > 0.5:
        main_emoji, odd_emoji = odd_emoji, main_emoji
    
    grid = [main_emoji] * total
    odd_positions = random.sample(range(total), odd_count)
    
    for pos in odd_positions:
        grid[pos] = odd_emoji
    
    return {
        "grid": grid,
        "rows": rows,
        "cols": cols,
        "main_emoji": main_emoji,
        "odd_emoji": odd_emoji,
        "odd_positions": set(odd_positions),
        "odd_count": odd_count,
        "found": set(),
        "mistakes": 0
    }

def create_emoji_keyboard(game_data, show_found=True):
    """Создание клавиатуры из эмодзи"""
    grid = game_data["grid"]
    rows = game_data["rows"]
    cols = game_data["cols"]
    found = game_data.get("found", set())
    
    buttons = []
    
    for r in range(rows):
        row_buttons = []
        for c in range(cols):
            position = r * cols + c
            
            if position in found:
                # Уже найденный - показываем галочку
                emoji = "✅"
            else:
                emoji = grid[position]
            
            row_buttons.append(
                InlineKeyboardButton(
                    text=emoji,
                    callback_data=f"pick_{position}"
                )
            )
        buttons.append(row_buttons)
    
    # Дополнительные кнопки
    buttons.append([
        InlineKeyboardButton(text="💡 Подсказка", callback_data="hint"),
        InlineKeyboardButton(text="🏳️ Сдаться", callback_data="give_up")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_difficulty_name(level):
    if level <= 3:
        return "🟢 Легко"
    elif level <= 6:
        return "🟡 Средне"
    elif level <= 10:
        return "🟠 Сложно"
    elif level <= 15:
        return "🔴 Очень сложно"
    else:
        return "💀 НЕВОЗМОЖНО"

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    player = get_player_data(message.from_user.id)
    
    text = f"""
🎮 **НАЙДИ ЛИШНИЙ ЭМОДЗИ** 🎮

Привет, {message.from_user.first_name}! 👋

━━━━━━━━━━━━━━━━━━━━━

📋 **Правила:**
• На поле много одинаковых эмодзи
• Один или несколько ОТЛИЧАЮТСЯ
• Нажми на лишний эмодзи!

━━━━━━━━━━━━━━━━━━━━━

📊 **Твой профиль:**
🏆 Рекорд: **{player['high_score']}**
📈 Уровень: **{player['level']}** {get_difficulty_name(player['level'])}
🎲 Игр: **{player['games_played']}**

━━━━━━━━━━━━━━━━━━━━━

🎯 **Уровни сложности:**
🟢 1-3: Легко различимые эмодзи
🟡 4-6: Похожие эмодзи
🟠 7-10: Очень похожие
🔴 11-15: Минимальные отличия
💀 16-20: ДЛЯ ЭКСПЕРТОВ!
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 ИГРАТЬ!", callback_data="new_game")],
        [
            InlineKeyboardButton(text="📊 Стата", callback_data="stats"),
            InlineKeyboardButton(text="🎚️ Уровень", callback_data="select_level")
        ],
        [InlineKeyboardButton(text="❓ Как играть", callback_data="help")]
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
    
    odd_text = "лишний" if game_data["odd_count"] == 1 else f"лишних: {game_data['odd_count']}"
    
    text = f"""
🎮 **УРОВЕНЬ {player['level']}** {get_difficulty_name(player['level'])}

💰 Очки: **{player['score']}** | 🔥 Серия: **{player['streak']}**

━━━━━━━━━━━━━━━━━━━━━

🔍 Найди {odd_text} эмодзи!
📐 Поле: {game_data['cols']}×{game_data['rows']} ({game_data['cols'] * game_data['rows']} шт.)

👇 **Нажми на лишний эмодзи:**
"""
    
    keyboard = create_emoji_keyboard(game_data)
    
    if edit and hasattr(message_or_callback, 'message'):
        await message_or_callback.message.edit_text(
            text, parse_mode="Markdown", reply_markup=keyboard
        )
    else:
        target = message_or_callback if hasattr(message_or_callback, 'answer') else message_or_callback.message
        await target.answer(text, parse_mode="Markdown", reply_markup=keyboard)

@dp.callback_query(F.data == "new_game")
async def callback_new_game(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    await start_new_game(callback.from_user.id, callback, state, edit=True)

@dp.callback_query(F.data.startswith("pick_"))
async def callback_pick(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    
    if "game" not in data:
        await callback.answer("Начни новую игру! /play", show_alert=True)
        return
    
    game_data = data["game"]
    position = int(callback.data.split("_")[1])
    player = get_player_data(callback.from_user.id)
    
    # Уже нашёл этот?
    if position in game_data["found"]:
        await callback.answer("Уже найдено! ✅", show_alert=False)
        return
    
    if position in game_data["odd_positions"]:
        # ПРАВИЛЬНО!
        game_data["found"].add(position)
        await state.update_data(game=game_data)
        
        # Нашёл все?
        if game_data["found"] == game_data["odd_positions"]:
            # ПОБЕДА!
            base_points = 10 * player["level"]
            mistake_penalty = game_data["mistakes"] * 2
            points = max(base_points - mistake_penalty, 5)
            
            player["score"] += points
            player["streak"] += 1
            player["games_played"] += 1
            
            if game_data["mistakes"] == 0:
                player["perfect_games"] += 1
                points += 5  # Бонус за идеальную игру
            
            # Повышение уровня
            level_up = False
            if player["streak"] % 3 == 0 and player["level"] < 20:
                player["level"] += 1
                level_up = True
            
            if player["score"] > player["high_score"]:
                player["high_score"] = player["score"]
            
            perfect = "🌟 ИДЕАЛЬНО! +5 бонус" if game_data["mistakes"] == 0 else ""
            level_msg = f"\n🆙 **УРОВЕНЬ {player['level']}!**" if level_up else ""
            
            text = f"""
🎉 **ПОБЕДА!** 🎉

━━━━━━━━━━━━━━━━━━━━━

✅ Лишний эмодзи: {game_data['odd_emoji']}
📦 Основной эмодзи: {game_data['main_emoji']}

💰 **+{points} очков!**
{perfect}
📊 Всего: **{player['score']}**
🔥 Серия побед: **{player['streak']}**
{level_msg}

━━━━━━━━━━━━━━━━━━━━━
"""
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="▶️ Следующий раунд!", callback_data="new_game")],
                [
                    InlineKeyboardButton(text="📊 Стата", callback_data="stats"),
                    InlineKeyboardButton(text="🏠 Меню", callback_data="menu")
                ]
            ])
            
            await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
            await state.clear()
        else:
            # Нашёл, но ещё есть другие
            remaining = len(game_data["odd_positions"]) - len(game_data["found"])
            await callback.answer(f"✅ Правильно! Осталось найти: {remaining}", show_alert=False)
            
            keyboard = create_emoji_keyboard(game_data)
            
            text = f"""
🎮 **УРОВЕНЬ {player['level']}** {get_difficulty_name(player['level'])}

💰 Очки: **{player['score']}** | 🔥 Серия: **{player['streak']}**

━━━━━━━━━━━━━━━━━━━━━

✅ Найдено: {len(game_data['found'])}/{game_data['odd_count']}
❌ Ошибок: {game_data['mistakes']}

👇 **Найди остальные:**
"""
            await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
    
    else:
        # ОШИБКА!
        game_data["mistakes"] += 1
        await state.update_data(game=game_data)
        
        if game_data["mistakes"] >= 3:
            # Слишком много ошибок - проигрыш
            player["streak"] = 0
            player["games_played"] += 1
            if player["level"] > 1:
                player["level"] -= 1
            
            # Показываем ответ
            answer_grid = []
            for r in range(game_data["rows"]):
                row_btns = []
                for c in range(game_data["cols"]):
                    pos = r * game_data["cols"] + c
                    if pos in game_data["odd_positions"]:
                        row_btns.append(InlineKeyboardButton(text="🎯", callback_data="none"))
                    else:
                        row_btns.append(InlineKeyboardButton(text=game_data["grid"][pos], callback_data="none"))
                answer_grid.append(row_btns)
            
            answer_grid.append([
                InlineKeyboardButton(text="🔄 Заново", callback_data="new_game"),
                InlineKeyboardButton(text="🏠 Меню", callback_data="menu")
            ])
            
            text = f"""
😢 **ПРОИГРЫШ!**

❌ 3 ошибки - игра окончена!

━━━━━━━━━━━━━━━━━━━━━

🎯 = правильный ответ

Лишний: {game_data['odd_emoji']}
Основной: {game_data['main_emoji']}

📉 Уровень: {player['level']}
🔥 Серия сброшена
"""
            
            await callback.message.edit_text(
                text, 
                parse_mode="Markdown", 
                reply_markup=InlineKeyboardMarkup(inline_keyboard=answer_grid)
            )
            await state.clear()
        else:
            # Ещё есть попытки
            remaining_tries = 3 - game_data["mistakes"]
            await callback.answer(
                f"❌ Неправильно! Осталось попыток: {remaining_tries}", 
                show_alert=True
            )
            
            keyboard = create_emoji_keyboard(game_data)
            
            text = f"""
🎮 **УРОВЕНЬ {player['level']}** {get_difficulty_name(player['level'])}

💰 Очки: **{player['score']}** | 🔥 Серия: **{player['streak']}**

━━━━━━━━━━━━━━━━━━━━━

❌ Ошибок: {game_data['mistakes']}/3
🔍 Найди лишний эмодзи!

👇 **Попробуй ещё:**
"""
            await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)

@dp.callback_query(F.data == "hint")
async def callback_hint(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    
    if "game" not in data:
        await callback.answer("Игра не найдена!", show_alert=True)
        return
    
    game_data = data["game"]
    hints_used = data.get("hints_used", 0)
    
    if hints_used >= 2:
        await callback.answer("Подсказки закончились! 🙈", show_alert=True)
        return
    
    # Находим не найденную позицию
    not_found = game_data["odd_positions"] - game_data["found"]
    if not not_found:
        await callback.answer("Все уже найдены!", show_alert=True)
        return
    
    odd_pos = list(not_found)[0]
    row = odd_pos // game_data["cols"] + 1
    col = odd_pos % game_data["cols"] + 1
    
    if hints_used == 0:
        hint = f"💡 Ряд: {row}"
    else:
        hint = f"💡 Ряд {row}, Колонка {col}"
    
    await state.update_data(hints_used=hints_used + 1)
    await callback.answer(hint, show_alert=True)

@dp.callback_query(F.data == "give_up")
async def callback_give_up(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    
    if "game" not in data:
        await callback.answer("Игра не найдена!", show_alert=True)
        return
    
    game_data = data["game"]
    player = get_player_data(callback.from_user.id)
    player["streak"] = 0
    
    # Показываем ответ
    answer_grid = []
    for r in range(game_data["rows"]):
        row_btns = []
        for c in range(game_data["cols"]):
            pos = r * game_data["cols"] + c
            if pos in game_data["odd_positions"]:
                row_btns.append(InlineKeyboardButton(text="🎯", callback_data="none"))
            else:
                row_btns.append(InlineKeyboardButton(text=game_data["grid"][pos], callback_data="none"))
        answer_grid.append(row_btns)
    
    answer_grid.append([
        InlineKeyboardButton(text="🔄 Новая игра", callback_data="new_game"),
        InlineKeyboardButton(text="🏠 Меню", callback_data="menu")
    ])
    
    text = f"""
🏳️ **СДАЛСЯ**

🎯 = лишний эмодзи

Лишний: {game_data['odd_emoji']}
Основной: {game_data['main_emoji']}
"""
    
    await callback.message.edit_text(
        text, 
        parse_mode="Markdown", 
        reply_markup=InlineKeyboardMarkup(inline_keyboard=answer_grid)
    )
    await state.clear()
    await callback.answer()

@dp.callback_query(F.data == "select_level")
async def callback_select_level(callback: types.CallbackQuery):
    player = get_player_data(callback.from_user.id)
    
    text = f"""
🎚️ **ВЫБОР УРОВНЯ**

Текущий: **{player['level']}** {get_difficulty_name(player['level'])}

Выбери стартовый уровень:
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1️⃣", callback_data="set_level_1"),
            InlineKeyboardButton(text="2️⃣", callback_data="set_level_2"),
            InlineKeyboardButton(text="3️⃣", callback_data="set_level_3"),
            InlineKeyboardButton(text="4️⃣", callback_data="set_level_4"),
            InlineKeyboardButton(text="5️⃣", callback_data="set_level_5"),
        ],
        [
            InlineKeyboardButton(text="6️⃣", callback_data="set_level_6"),
            InlineKeyboardButton(text="7️⃣", callback_data="set_level_7"),
            InlineKeyboardButton(text="8️⃣", callback_data="set_level_8"),
            InlineKeyboardButton(text="9️⃣", callback_data="set_level_9"),
            InlineKeyboardButton(text="🔟", callback_data="set_level_10"),
        ],
        [
            InlineKeyboardButton(text="11", callback_data="set_level_11"),
            InlineKeyboardButton(text="12", callback_data="set_level_12"),
            InlineKeyboardButton(text="13", callback_data="set_level_13"),
            InlineKeyboardButton(text="14", callback_data="set_level_14"),
            InlineKeyboardButton(text="15", callback_data="set_level_15"),
        ],
        [
            InlineKeyboardButton(text="16", callback_data="set_level_16"),
            InlineKeyboardButton(text="17", callback_data="set_level_17"),
            InlineKeyboardButton(text="18", callback_data="set_level_18"),
            InlineKeyboardButton(text="19", callback_data="set_level_19"),
            InlineKeyboardButton(text="20", callback_data="set_level_20"),
        ],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="menu")]
    ])
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data.startswith("set_level_"))
async def callback_set_level(callback: types.CallbackQuery):
    level = int(callback.data.split("_")[2])
    player = get_player_data(callback.from_user.id)
    player["level"] = level
    
    await callback.answer(f"Уровень установлен: {level} {get_difficulty_name(level)}", show_alert=True)
    await callback_select_level(callback)

@dp.callback_query(F.data == "stats")
async def callback_stats(callback: types.CallbackQuery):
    player = get_player_data(callback.from_user.id)
    
    # Определяем ранг
    if player["high_score"] >= 1000:
        rank = "💎 Легенда"
    elif player["high_score"] >= 500:
        rank = "👑 Мастер"
    elif player["high_score"] >= 200:
        rank = "🥇 Эксперт"
    elif player["high_score"] >= 100:
        rank = "🥈 Продвинутый"
    elif player["high_score"] >= 50:
        rank = "🥉 Опытный"
    else:
        rank = "🎮 Новичок"
    
    text = f"""
📊 **СТАТИСТИКА**

👤 {callback.from_user.first_name}
🎖️ Ранг: **{rank}**

━━━━━━━━━━━━━━━━━━━━━

🏆 Рекорд: **{player['high_score']}**
💰 Текущие очки: **{player['score']}**
📈 Уровень: **{player['level']}** {get_difficulty_name(player['level'])}
🔥 Серия побед: **{player['streak']}**
🎲 Игр сыграно: **{player['games_played']}**
⭐ Идеальных игр: **{player['perfect_games']}**

━━━━━━━━━━━━━━━━━━━━━

🎖️ **Ранги:**
🎮 Новичок: 0+
🥉 Опытный: 50+
🥈 Продвинутый: 100+
🥇 Эксперт: 200+
👑 Мастер: 500+
💎 Легенда: 1000+
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Играть", callback_data="new_game")],
        [InlineKeyboardButton(text="🔄 Сбросить", callback_data="reset_confirm")],
        [InlineKeyboardButton(text="🏠 Меню", callback_data="menu")]
    ])
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data == "reset_confirm")
async def callback_reset_confirm(callback: types.CallbackQuery):
    text = "⚠️ **Точно сбросить весь прогресс?**"
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да", callback_data="reset_yes"),
            InlineKeyboardButton(text="❌ Нет", callback_data="stats")
        ]
    ])
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data == "reset_yes")
async def callback_reset(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    players_data[user_id] = {
        "score": 0,
        "high_score": 0,
        "level": 1,
        "streak": 0,
        "games_played": 0,
        "perfect_games": 0
    }
    
    await callback.answer("✅ Прогресс сброшен!", show_alert=True)
    await callback_stats(callback)

@dp.callback_query(F.data == "menu")
async def callback_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    player = get_player_data(callback.from_user.id)
    
    text = f"""
🎮 **НАЙДИ ЛИШНИЙ ЭМОДЗИ**

📊 Рекорд: **{player['high_score']}** 🏆
📈 Уровень: **{player['level']}** {get_difficulty_name(player['level'])}
🔥 Серия: **{player['streak']}**
"""
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 ИГРАТЬ!", callback_data="new_game")],
        [
            InlineKeyboardButton(text="📊 Стата", callback_data="stats"),
            InlineKeyboardButton(text="🎚️ Уровень", callback_data="select_level")
        ],
        [InlineKeyboardButton(text="❓ Помощь", callback_data="help")]
    ])
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data == "help")
async def callback_help(callback: types.CallbackQuery):
    text = """
❓ **КАК ИГРАТЬ**

━━━━━━━━━━━━━━━━━━━━━

1️⃣ Смотри на поле с эмодзи
2️⃣ Найди тот, что ОТЛИЧАЕТСЯ
3️⃣ Нажми на него!

━━━━━━━━━━━━━━━━━━━━━
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Играть", callback_data="new_game")],
        [InlineKeyboardButton(text="🏠 Меню", callback_data="menu")]
    ])
    
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)
    await callback.answer()

@dp.callback_query(F.data == "none")
async def callback_none(callback: types.CallbackQuery):
    await callback.answer()

async def main():
    print("🎮 Бот 'Найди лишний эмодзи' запущен!")
    print("📊 Уровни: 1-20")
    print("🔍 Пар эмодзи:", len(EASY_PAIRS + MEDIUM_PAIRS + HARD_PAIRS + EXTREME_PAIRS + INSANE_PAIRS))
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

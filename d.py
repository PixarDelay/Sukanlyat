import logging
from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from datetime import datetime, timedelta
import configparser
import re
import json
from pathlib import Path
import random
import asyncio
from collections import defaultdict

# Загрузка конфигурации
config = configparser.ConfigParser()
config.read('c.ini')

# Эмодзи для слотов
SLOT_EMOJI = ['🍎', '🍊', '🍋', '🍒', '🔔', '💎', '7️⃣']

# Система сохранения наказаний
class PunishmentSystem:
    def __init__(self):
        self.data_file = config.get('Storage', 'data_file', fallback='punishments.json')
        self.punishments = self.load_data()
        
    def load_data(self):
        try:
            with open(self.data_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            return {
                "bans": [],
                "mutes": [],
                "warns": []
            }
            
    def save_data(self):
        with open(self.data_file, 'w', encoding='utf-8') as f:
            json.dump(self.punishments, f, indent=4, ensure_ascii=False)
            
    def add_punishment(self, type_name, data):
        self.punishments[type_name].append(data)
        self.save_data()
        
    def remove_punishment(self, type_name, user_id):
        self.punishments[type_name] = [
            p for p in self.punishments[type_name] 
            if p['user_id'] != user_id
        ]
        self.save_data()
        
    def get_active_punishments(self, type_name):
        current_time = datetime.now().timestamp()
        return [
            p for p in self.punishments[type_name]
            if p.get('until_date', float('inf')) > current_time
        ]
        
    def get_user_warns(self, user_id):
        return [p for p in self.punishments['warns'] if p['user_id'] == user_id]
        
    async def check_expired_punishments(self, bot):
        current_time = datetime.now().timestamp()
        try:
            chat_id = config.get('Chat', 'chat_id')
        except:
            logging.error("Chat ID not found in config!")
            return
            
        if not chat_id:
            logging.error("Chat ID is empty!")
            return
            
        for ban in self.punishments['bans']:
            if ban.get('until_date', float('inf')) <= current_time:
                try:
                    await bot.unban_chat_member(chat_id, ban['user_id'])
                    self.remove_punishment('bans', ban['user_id'])
                except Exception as e:
                    logging.error(f"Error unbanning user {ban['user_id']}: {e}")
                    
        for mute in self.punishments['mutes']:
            if mute.get('until_date', float('inf')) <= current_time:
                try:
                    await bot.restrict_chat_member(
                        chat_id,
                        mute['user_id'],
                        permissions=types.ChatPermissions(
                            can_send_messages=True,
                            can_send_media_messages=True,
                            can_send_other_messages=True,
                            can_add_web_page_previews=True
                        )
                    )
                    self.remove_punishment('mutes', mute['user_id'])
                except Exception as e:
                    logging.error(f"Error unmuting user {mute['user_id']}: {e}")

# Инициализация бота
bot = Bot(token=config['Bot']['token'])
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
punishment_system = PunishmentSystem()
logging.basicConfig(level=logging.INFO)

# Хранение данных
user_data = {}
spam_data = {}

# Настройки защиты
protection_settings = {
    "antiword": config.getboolean('Protection', 'antiword', fallback=True),
    "anticaps": config.getboolean('Protection', 'anticaps', fallback=True),
    "antispam": config.getboolean('Protection', 'antispam', fallback=True)
}

# Эмодзи и декорации
EMOJIS = {
    # Модерация
    "ban": "⛔️", "mute": "🔇", "warn": "⚠️", "unban": "♻️", "unmute": "🔊", "unwarn": "🔄",
    
    # Декоративные
    "star": "⭐️", "sparkles": "✨", "hammer": "🔨", "shield": "🛡", "crown": "👑",
    "globe": "🌍", "lock": "🔒", "unlock": "🔓", "time": "⏰", "info": "ℹ️",
    "alert": "🚨", "check": "✅", "cross": "❌", "fire": "🔥", "lightning": "⚡️",
    "diamond": "💎", "scroll": "📜", "book": "📚", "gear": "⚙️", "key": "🔑",
    "bell": "🔔", "pin": "📌", "label": "🏷", "guard": "💂‍♂️", "slot": "🎰",
    "page": "📄", "arrow_right": "➡️", "arrow_left": "⬅️", "number": "#️⃣", "id": "🆔", "chart": "📊", "users": "👥", "time": "⏱",
    
    # Игры
    "game_die": "🎲", "coin": "🪙", "casino": "🎯",
    "rock": "🗿", "paper": "📄", "scissors": "✂️",
    "win": "🏆", "lose": "💔", "draw": "🤝"
}

DECORATIONS = {
    "header": f"{EMOJIS['sparkles']} ═══ {EMOJIS['shield']} ═══ {EMOJIS['sparkles']}",
    "footer": f"{EMOJIS['sparkles']} ════════ {EMOJIS['sparkles']}",
    "separator": "┄┄┄┄┄┄┄┄┄┄┄┄┄",
    "bullet": "•",
    "arrow": "→"
}

# Вспомогательные функции
async def check_chat(message: types.Message):
    try:
        allowed_chat = config.get('Chat', 'chat_id', fallback=None)
        if not allowed_chat:
            logging.error("Chat ID not found in config!")
            return True
        return str(message.chat.id) == allowed_chat
    except:
        logging.error("Error checking chat ID!")
        return True

async def is_admin(message: types.Message):
    if not await check_chat(message):
        return False
    user = await bot.get_chat_member(message.chat.id, message.from_user.id)
    return user.is_chat_admin()

def parse_time(time_str):
    time_units = {"d": 86400, "h": 3600, "m": 60}
    time_pattern = re.compile(r"(\d+)([dhm])")
    match = time_pattern.match(time_str)
    if match:
        value, unit = match.groups()
        return int(value) * time_units[unit]
    return None

def format_time(seconds):
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    parts = []
    if days: parts.append(f"{days}д")
    if hours: parts.append(f"{hours}ч")
    if minutes: parts.append(f"{minutes}м")
    return " ".join(parts) or "1м"

async def get_user_mention(chat_id, user_id):
    try:
        user = await bot.get_chat_member(chat_id, user_id)
        return user.user.get_mention()
    except:
        return f"[Пользователь](tg://user?id={user_id})"

# Команды приветствия и помощи
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    response = f"""
{DECORATIONS['header']}
{EMOJIS['crown']} **FPI-КЛАН БОТ** {EMOJIS['crown']}
{DECORATIONS['separator']}

{EMOJIS['guard']} Привет! Я бот-модератор чата FPI-КЛАН
{EMOJIS['shield']} Помогаю поддерживать порядок и делаю чат лучше

{EMOJIS['info']} Используй /help для просмотра команд
{EMOJIS['game_die']} А также у меня есть крутые мини-игры!

{DECORATIONS['footer']}
"""
    await message.reply(response, parse_mode="Markdown")

@dp.message_handler(commands=['help'])
async def cmd_help(message: types.Message):
    response = f"""
{DECORATIONS['header']}
{EMOJIS['book']} **СПИСОК КОМАНД** {EMOJIS['book']}
{DECORATIONS['separator']}

{EMOJIS['shield']} *Модерация:*
{EMOJIS['ban']} `/ban [ID/reply] [время] [причина]` - Бан
{EMOJIS['mute']} `/mute [ID/reply] [время] [причина]` - Мут
{EMOJIS['warn']} `/warn [ID/reply] [причина]` - Варн
{EMOJIS['unban']} `/unban [ID]` - Разбан
{EMOJIS['unmute']} `/unmute [ID/reply]` - Размут
{EMOJIS['unwarn']} `/unwarn [ID/reply]` - Снять варн

{EMOJIS['scroll']} *Информация:*
{EMOJIS['page']} `/bans` - Список банов
{EMOJIS['page']} `/mutes` - Список мутов
{EMOJIS['page']} `/warns` - Список варнов
{EMOJIS['info']} `/about` - О боте

{EMOJIS['game_die']} *Мини-игры:*
{EMOJIS['slot']} `/slot` - Слоты
{EMOJIS['game_die']} `/dice` - Кости
{EMOJIS['coin']} `/flip` - Монетка
{EMOJIS['casino']} `/casino` - Казино

{DECORATIONS['footer']}
"""
    await message.reply(response, parse_mode="Markdown")

# Словарь наказаний
PUNISHMENTS = {
    "spam": "Спам",
    "flood": "Флуд",
    "caps": "Капс",
    "ads": "Реклама",
    "nsfw": "18+ контент",
    "insult": "Оскорбления",
    "harassment": "Домогательства",
    "raid": "Рейд",
    "scam": "Мошенничество",
    "forbidden_symbols": "Запрещенные символы"
}

# Мини-игры
@dp.message_handler(commands=['slot'])
async def cmd_slot(message: types.Message):
    slots = [random.choice(['🍎', '🍊', '🍋', '🍒', '🔔', '💎', '7️⃣']) for _ in range(3)]
    
    msg = await message.reply("🎰 | - | - | - |")
    await asyncio.sleep(0.5)
    await msg.edit_text(f"🎰 | {slots[0]} | - | - |")
    await asyncio.sleep(0.5)
    await msg.edit_text(f"🎰 | {slots[0]} | {slots[1]} | - |")
    await asyncio.sleep(0.5)
    
    result = f"""
{DECORATIONS['header']}
{EMOJIS['slot']} **СЛОТЫ** {EMOJIS['slot']}
{DECORATIONS['separator']}

🎰 | {slots[0]} | {slots[1]} | {slots[2]} |

"""
    
    if len(set(slots)) == 1:
        result += f"\n{EMOJIS['win']} **ДЖЕКПОТ!** {EMOJIS['win']}"
    elif len(set(slots)) == 2:
        result += f"\n{EMOJIS['star']} *Неплохо!* {EMOJIS['star']}"
    else:
        result += f"\n{EMOJIS['lose']} *Попробуйте снова* {EMOJIS['lose']}"
        
    result += f"\n\n{DECORATIONS['footer']}"
    await msg.edit_text(result, parse_mode="Markdown")

@dp.message_handler(commands=['casino'])
async def cmd_casino(message: types.Message):
    numbers = [random.randint(0, 9) for _ in range(3)]
    
    msg = await message.reply(f"{EMOJIS['casino']} | ? | ? | ? |")
    await asyncio.sleep(0.7)
    await msg.edit_text(f"{EMOJIS['casino']} | {numbers[0]} | ? | ? |")
    await asyncio.sleep(0.7)
    await msg.edit_text(f"{EMOJIS['casino']} | {numbers[0]} | {numbers[1]} | ? |")
    await asyncio.sleep(0.7)
    
    response = f"""
{DECORATIONS['header']}
{EMOJIS['casino']} **КАЗИНО** {EMOJIS['casino']}
{DECORATIONS['separator']}

{EMOJIS['casino']} | {numbers[0]} | {numbers[1]} | {numbers[2]} |

"""
    
    if len(set(numbers)) == 1:
        response += f"\n{EMOJIS['win']} **ДЖЕКПОТ!** {EMOJIS['win']}"
    elif len(set(numbers)) == 2:
        response += f"\n{EMOJIS['star']} *Хорошая комбинация!* {EMOJIS['star']}"
    else:
        response += f"\n{EMOJIS['lose']} *Попробуйте ещё раз* {EMOJIS['lose']}"
        
    response += f"\n\n{DECORATIONS['footer']}"
    await msg.edit_text(response, parse_mode="Markdown")

@dp.message_handler(commands=['dice'])
async def cmd_dice(message: types.Message):
    dice1 = random.randint(1, 6)
    dice2 = random.randint(1, 6)
    total = dice1 + dice2
    
    response = f"""
{DECORATIONS['header']}
{EMOJIS['game_die']} **КОСТИ** {EMOJIS['game_die']}
{DECORATIONS['separator']}

{EMOJIS['game_die']} Первая кость: *{dice1}*
{EMOJIS['game_die']} Вторая кость: *{dice2}*

{EMOJIS['star']} Сумма: *{total}*

{DECORATIONS['footer']}
"""
    await message.reply(response, parse_mode="Markdown")

@dp.message_handler(commands=['flip'])
async def cmd_flip(message: types.Message):
    result = random.choice(["ОРЁЛ", "РЕШКА"])
    emoji = "🦅" if result == "ОРЁЛ" else "👑"
    
    msg = await message.reply(f"{EMOJIS['coin']} Подбрасываем монетку...")
    await asyncio.sleep(1)
    
    response = f"""
{DECORATIONS['header']}
{EMOJIS['coin']} **МОНЕТКА** {EMOJIS['coin']}
{DECORATIONS['separator']}

{emoji} Выпало: *{result}*

{DECORATIONS['footer']}
"""
    await msg.edit_text(response, parse_mode="Markdown")

        # Команды модерации
        
@dp.message_handler(commands=['bans'])
async def cmd_bans(message: types.Message):
    if not await is_admin(message):
        return await message.reply(f"{EMOJIS['cross']} У вас недостаточно прав")
        
    active_bans = punishment_system.get_active_punishments('bans')
    
    if not active_bans:
        return await message.reply(f"{EMOJIS['info']} Активные баны отсутствуют")
    
    response = f"""
{DECORATIONS['header']}
{EMOJIS['ban']} **СПИСОК БАНОВ** {EMOJIS['ban']}
{DECORATIONS['separator']}
"""
    
    for ban in active_bans:
        user_mention = await get_user_mention(message.chat.id, ban['user_id'])
        until_date = datetime.fromtimestamp(ban['until_date']) if ban.get('until_date') else None
        duration = f"до {until_date.strftime('%d.%m.%Y %H:%M')}" if until_date else "навсегда"
        
        response += f"""
{EMOJIS['guard']} *Нарушитель:* {user_mention}
{EMOJIS['time']} *Срок:* {duration}
{EMOJIS['scroll']} *Причина:* {ban['reason']}
{EMOJIS['shield']} *Выдал:* {ban['admin_name']}
{DECORATIONS['separator']}
"""
    
    response += f"\n{DECORATIONS['footer']}"
    await message.reply(response, parse_mode="Markdown")

@dp.message_handler(commands=['mutes'])
async def cmd_mutes(message: types.Message):
    if not await is_admin(message):
        return await message.reply(f"{EMOJIS['cross']} У вас недостаточно прав")
        
    active_mutes = punishment_system.get_active_punishments('mutes')
    
    if not active_mutes:
        return await message.reply(f"{EMOJIS['info']} Активные муты отсутствуют")
    
    response = f"""
{DECORATIONS['header']}
{EMOJIS['mute']} **СПИСОК МУТОВ** {EMOJIS['mute']}
{DECORATIONS['separator']}
"""
    
    for mute in active_mutes:
        user_mention = await get_user_mention(message.chat.id, mute['user_id'])
        until_date = datetime.fromtimestamp(mute['until_date'])
        remaining_time = format_time((until_date - datetime.now()).total_seconds())
        
        response += f"""
{EMOJIS['guard']} *Нарушитель:* {user_mention}
{EMOJIS['time']} *Осталось:* {remaining_time}
{EMOJIS['scroll']} *Причина:* {mute['reason']}
{EMOJIS['shield']} *Выдал:* {mute['admin_name']}
{DECORATIONS['separator']}
"""
    
    response += f"\n{DECORATIONS['footer']}"
    await message.reply(response, parse_mode="Markdown")

@dp.message_handler(commands=['warns'])
async def cmd_warns(message: types.Message):
    if not await is_admin(message):
        return await message.reply(f"{EMOJIS['cross']} У вас недостаточно прав")
        
    all_warns = punishment_system.punishments['warns']
    
    if not all_warns:
        return await message.reply(f"{EMOJIS['info']} Предупреждения отсутствуют")
    
    # Группируем варны по пользователям
    warns_by_user = {}
    for warn in all_warns:
        user_id = warn['user_id']
        if user_id not in warns_by_user:
            warns_by_user[user_id] = []
        warns_by_user[user_id].append(warn)
    
    response = f"""
{DECORATIONS['header']}
{EMOJIS['warn']} **СПИСОК ВАРНОВ** {EMOJIS['warn']}
{DECORATIONS['separator']}
"""
    
    for user_id, warns in warns_by_user.items():
        user_mention = await get_user_mention(message.chat.id, user_id)
        
        response += f"""
{EMOJIS['guard']} *Нарушитель:* {user_mention}
{EMOJIS['alert']} *Варнов:* {len(warns)}/3
"""
        
        for warn in warns:
            warn_date = datetime.fromtimestamp(warn['date']).strftime('%d.%m.%Y %H:%M')
            response += f"""
{EMOJIS['scroll']} *Причина:* {warn['reason']}
{EMOJIS['shield']} *Выдал:* {warn['admin_name']}
{EMOJIS['time']} *Дата:* {warn_date}
"""
        response += f"\n{DECORATIONS['separator']}"
    
    response += f"\n{DECORATIONS['footer']}"
    await message.reply(response, parse_mode="Markdown")
        
@dp.message_handler(commands=['ban'])
async def cmd_ban(message: types.Message):
    if not await is_admin(message):
        return await message.reply(f"{EMOJIS['cross']} У вас недостаточно прав")
        
    args = message.get_args().split()
    if not args:
        if not message.reply_to_message:
            return await message.reply(f"{EMOJIS['info']} Использование: `/ban [ID/reply] [время(1d/1h/30m)] [причина]`", parse_mode="Markdown")
        user_id = message.reply_to_message.from_user.id
        user_mention = message.reply_to_message.from_user.get_mention()
    else:
        try:
            user_id = int(args[0])
            user_mention = await get_user_mention(message.chat.id, user_id)
        except:
            return await message.reply(f"{EMOJIS['cross']} Неверный ID пользователя")
    
    if len(args) > 1 and parse_time(args[1]):
        ban_time = parse_time(args[1])
        until_date = datetime.now() + timedelta(seconds=ban_time)
        reason = " ".join(args[2:]) if len(args) > 2 else "Не указана"
    else:
        ban_time = None
        until_date = None
        reason = " ".join(args[1:]) if len(args) > 1 else "Не указана"
    
    try:
        await bot.ban_chat_member(
            message.chat.id,
            user_id,
            until_date=until_date
        )
        
        punishment_system.add_punishment('bans', {
            "user_id": user_id,
            "admin_id": message.from_user.id,
            "admin_name": message.from_user.get_mention(),
            "reason": reason,
            "until_date": until_date.timestamp() if until_date else None,
            "date": datetime.now().timestamp()
        })
        
        response = f"""
{DECORATIONS['header']}
{EMOJIS['ban']} **ПОЛЬЗОВАТЕЛЬ ЗАБАНЕН** {EMOJIS['ban']}
{DECORATIONS['separator']}

{EMOJIS['guard']} *Нарушитель:* {user_mention}
{EMOJIS['time']} *Срок:* {'Навсегда' if not ban_time else format_time(ban_time)}
{EMOJIS['scroll']} *Причина:* {reason}
{EMOJIS['shield']} *Модератор:* {message.from_user.get_mention()}

{DECORATIONS['footer']}
"""
        await message.reply(response, parse_mode="Markdown")
        
    except Exception as e:
        await message.reply(f"{EMOJIS['cross']} Ошибка: {str(e)}")

@dp.message_handler(commands=['about'])
async def cmd_about(message: types.Message):
    response = f"""
{DECORATIONS['header']}
{EMOJIS['star']} **О БОТЕ** {EMOJIS['star']}
{DECORATIONS['separator']}

{EMOJIS['crown']} *Создатель:* {config['Bot']['creator']}
{EMOJIS['globe']} *Контакт:* {config['Bot']['contact']}
{EMOJIS['gear']} *Версия:* {config['Bot']['version']}

{EMOJIS['scroll']} *Возможности:*
• Модерация чата
• Система предупреждений
• Защита от спама
• Защита от флуда
• Защита от капса
• Мини-игры

{EMOJIS['sparkles']} Сделано с любовью для FPI-КЛАН

{DECORATIONS['footer']}
"""
    await message.reply(response, parse_mode="Markdown")

@dp.message_handler(commands=['mute'])
async def cmd_mute(message: types.Message):
    if not await is_admin(message):
        return await message.reply(f"{EMOJIS['cross']} У вас недостаточно прав")
        
    args = message.get_args().split()
    if not args:
        if not message.reply_to_message:
            return await message.reply(f"{EMOJIS['info']} Использование: `/mute [ID/reply] [время(1d/1h/30m)] [причина]`", parse_mode="Markdown")
        user_id = message.reply_to_message.from_user.id
        user_mention = message.reply_to_message.from_user.get_mention()
    else:
        try:
            user_id = int(args[0])
            user_mention = await get_user_mention(message.chat.id, user_id)
        except:
            return await message.reply(f"{EMOJIS['cross']} Неверный ID пользователя")
    
    if len(args) > 1 and parse_time(args[1]):
        mute_time = parse_time(args[1])
        until_date = datetime.now() + timedelta(seconds=mute_time)
        reason = " ".join(args[2:]) if len(args) > 2 else "Не указана"
    else:
        mute_time = 3600  # 1 час по умолчанию
        until_date = datetime.now() + timedelta(seconds=mute_time)
        reason = " ".join(args[1:]) if len(args) > 1 else "Не указана"
    
    try:
        await bot.restrict_chat_member(
            message.chat.id,
            user_id,
            permissions=types.ChatPermissions(can_send_messages=False),
            until_date=until_date
        )
        
        punishment_system.add_punishment('mutes', {
            "user_id": user_id,
            "admin_id": message.from_user.id,
            "admin_name": message.from_user.get_mention(),
            "reason": reason,
            "until_date": until_date.timestamp(),
            "date": datetime.now().timestamp()
        })
        
        response = f"""
{DECORATIONS['header']}
{EMOJIS['mute']} **ПОЛЬЗОВАТЕЛЬ ЗАМУЧЕН** {EMOJIS['mute']}
{DECORATIONS['separator']}

{EMOJIS['guard']} *Нарушитель:* {user_mention}
{EMOJIS['time']} *Срок:* {format_time(mute_time)}
{EMOJIS['scroll']} *Причина:* {reason}
{EMOJIS['shield']} *Модератор:* {message.from_user.get_mention()}

{DECORATIONS['footer']}
"""
        await message.reply(response, parse_mode="Markdown")
        
    except Exception as e:
        await message.reply(f"{EMOJIS['cross']} Ошибка: {str(e)}")

@dp.message_handler(commands=['warn'])
async def cmd_warn(message: types.Message):
    if not await is_admin(message):
        return await message.reply(f"{EMOJIS['cross']} У вас недостаточно прав")
        
    args = message.get_args().split()
    if not args and not message.reply_to_message:
        return await message.reply(f"{EMOJIS['info']} Использование: `/warn [ID/reply] [причина]`", parse_mode="Markdown")
        
    if message.reply_to_message:
        user_id = message.reply_to_message.from_user.id
        user_mention = message.reply_to_message.from_user.get_mention()
        reason = " ".join(args) if args else "Не указана"
    else:
        try:
            user_id = int(args[0])
            user_mention = await get_user_mention(message.chat.id, user_id)
            reason = " ".join(args[1:]) if len(args) > 1 else "Не указана"
        except:
            return await message.reply(f"{EMOJIS['cross']} Неверный ID пользователя")
    
    if user_id not in user_data:
        user_data[user_id] = {"warns": 0}
    user_data[user_id]["warns"] += 1
    warns_count = user_data[user_id]["warns"]
    
    punishment_system.add_punishment('warns', {
        "user_id": user_id,
        "admin_id": message.from_user.id,
        "admin_name": message.from_user.get_mention(),
        "reason": reason,
        "warn_num": warns_count,
        "date": datetime.now().timestamp()
    })
    
    response = f"""
{DECORATIONS['header']}
{EMOJIS['warn']} **ВЫДАНО ПРЕДУПРЕЖДЕНИЕ** {EMOJIS['warn']}
{DECORATIONS['separator']}

{EMOJIS['guard']} *Нарушитель:* {user_mention}
{EMOJIS['alert']} *Варнов:* {warns_count}/3
{EMOJIS['scroll']} *Причина:* {reason}
{EMOJIS['shield']} *Модератор:* {message.from_user.get_mention()}

"""
    
    if warns_count >= 3:
        mute_duration = timedelta(hours=3)
        until_date = datetime.now() + mute_duration
        
        await bot.restrict_chat_member(
            message.chat.id,
            user_id,
            permissions=types.ChatPermissions(can_send_messages=False),
            until_date=until_date
        )
        
        punishment_system.add_punishment('mutes', {
            "user_id": user_id,
            "admin_id": message.from_user.id,
            "admin_name": "Система варнов",
            "reason": "Превышен лимит предупреждений (3/3)",
            "until_date": until_date.timestamp(),
            "date": datetime.now().timestamp()
        })
        
        response += f"""
{EMOJIS['mute']} **АВТОМАТИЧЕСКИЙ МУТ НА 3 ЧАСА**
{EMOJIS['info']} *Причина:* Превышен лимит предупреждений
"""
        user_data[user_id]["warns"] = 0
        
    response += f"\n{DECORATIONS['footer']}"
    await message.reply(response, parse_mode="Markdown")
    # Команды снятия наказаний
@dp.message_handler(commands=['unban'])
async def cmd_unban(message: types.Message):
    if not await is_admin(message):
        return await message.reply(f"{EMOJIS['cross']} У вас недостаточно прав")
        
    try:
        args = message.get_args().split()
        if not args:
            return await message.reply(f"{EMOJIS['info']} Использование: `/unban [ID]`", parse_mode="Markdown")
            
        user_id = int(args[0])
        user_mention = await get_user_mention(message.chat.id, user_id)
        
        await bot.unban_chat_member(message.chat.id, user_id)
        punishment_system.remove_punishment('bans', user_id)
        
        response = f"""
{DECORATIONS['header']}
{EMOJIS['unban']} **РАЗБАН ПОЛЬЗОВАТЕЛЯ** {EMOJIS['unban']}
{DECORATIONS['separator']}

{EMOJIS['guard']} *Пользователь:* {user_mention}
{EMOJIS['shield']} *Модератор:* {message.from_user.get_mention()}

{DECORATIONS['footer']}
"""
        await message.reply(response, parse_mode="Markdown")
        
    except Exception as e:
        await message.reply(f"{EMOJIS['cross']} Ошибка: {str(e)}")

@dp.message_handler(commands=['unmute'])
async def cmd_unmute(message: types.Message):
    if not await is_admin(message):
        return await message.reply(f"{EMOJIS['cross']} У вас недостаточно прав")
        
    try:
        if message.reply_to_message:
            user_id = message.reply_to_message.from_user.id
            user_mention = message.reply_to_message.from_user.get_mention()
        else:
            args = message.get_args().split()
            if not args:
                return await message.reply(f"{EMOJIS['info']} Использование: `/unmute [ID/reply]`", parse_mode="Markdown")
            user_id = int(args[0])
            user_mention = await get_user_mention(message.chat.id, user_id)
        
        await bot.restrict_chat_member(
            message.chat.id,
            user_id,
            permissions=types.ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True
            )
        )
        
        punishment_system.remove_punishment('mutes', user_id)
        
        response = f"""
{DECORATIONS['header']}
{EMOJIS['unmute']} **МУТ СНЯТ** {EMOJIS['unmute']}
{DECORATIONS['separator']}

{EMOJIS['guard']} *Пользователь:* {user_mention}
{EMOJIS['shield']} *Модератор:* {message.from_user.get_mention()}

{DECORATIONS['footer']}
"""
        await message.reply(response, parse_mode="Markdown")
        
    except Exception as e:
        await message.reply(f"{EMOJIS['cross']} Ошибка: {str(e)}")

@dp.message_handler(commands=['unwarn'])
async def cmd_unwarn(message: types.Message):
    if not await is_admin(message):
        return await message.reply(f"{EMOJIS['cross']} У вас недостаточно прав")
        
    try:
        if message.reply_to_message:
            user_id = message.reply_to_message.from_user.id
            user_mention = message.reply_to_message.from_user.get_mention()
        else:
            args = message.get_args().split()
            if not args:
                return await message.reply(f"{EMOJIS['info']} Использование: `/unwarn [ID/reply]`", parse_mode="Markdown")
            user_id = int(args[0])
            user_mention = await get_user_mention(message.chat.id, user_id)
        
        user_warns = punishment_system.get_user_warns(user_id)
        if not user_warns:
            return await message.reply(f"{EMOJIS['info']} У пользователя нет предупреждений")
        
        # Удаляем последнее предупреждение
        punishment_system.punishments['warns'].remove(user_warns[-1])
        punishment_system.save_data()
        
        # Обновляем счетчик варнов
        if user_id in user_data:
            user_data[user_id]["warns"] = max(0, user_data[user_id]["warns"] - 1)
        
        response = f"""
{DECORATIONS['header']}
{EMOJIS['unwarn']} **СНЯТО ПРЕДУПРЕЖДЕНИЕ** {EMOJIS['unwarn']}
{DECORATIONS['separator']}

{EMOJIS['guard']} *Пользователь:* {user_mention}
{EMOJIS['alert']} *Осталось варнов:* {len(user_warns)-1}/3
{EMOJIS['shield']} *Модератор:* {message.from_user.get_mention()}

{DECORATIONS['footer']}
"""
        await message.reply(response, parse_mode="Markdown")
        
    except Exception as e:
        await message.reply(f"{EMOJIS['cross']} Ошибка: {str(e)}")

# Защита от спама/капса/флуда
@dp.message_handler()
async def handle_messages(message: types.Message):
    if not await check_chat(message):
        return
        
    user_id = message.from_user.id
    current_time = datetime.now()
    text = message.text or ""
    
    # Проверка на спам символы
    if re.search(r'꙰|ᡃ⃝|⃟', text):
        await message.delete()
        response = f"""
{DECORATIONS['header']}
{EMOJIS['alert']} **ОБНАРУЖЕНЫ ЗАПРЕЩЁННЫЕ СИМВОЛЫ** {EMOJIS['alert']}
{DECORATIONS['separator']}

{EMOJIS['guard']} *Нарушитель:* {message.from_user.get_mention()}
{EMOJIS['cross']} *Действие:* Сообщение удалено

{DECORATIONS['footer']}
"""
        await message.answer(response, parse_mode="Markdown")
        return

    # Антикапс
    if protection_settings["anticaps"] and len(text) > 10:
        caps_ratio = sum(1 for c in text if c.isupper()) / len(text)
        if caps_ratio > 0.7:  # Если больше 70% текста в капсе
            await message.delete()
            if user_id not in user_data:
                user_data[user_id] = {"warns": 0}
            user_data[user_id]["warns"] += 1
            warns_count = user_data[user_id]["warns"]
            
            response = f"""
{DECORATIONS['header']}
{EMOJIS['alert']} **ОБНАРУЖЕН КАПС** {EMOJIS['alert']}
{DECORATIONS['separator']}

{EMOJIS['guard']} *Нарушитель:* {message.from_user.get_mention()}
{EMOJIS['scroll']} *Наказание:* Варн + удаление сообщения
{EMOJIS['alert']} *Варнов:* {warns_count}/3

{DECORATIONS['footer']}
"""
            await message.answer(response, parse_mode="Markdown")

    # Антиспам
    if protection_settings["antispam"]:
        if user_id not in spam_data:
            spam_data[user_id] = {"messages": [], "last_time": current_time.timestamp()}
            
        messages = spam_data[user_id]["messages"]
        messages = [t for t in messages if (current_time - t).total_seconds() < float(config['AntiSpam']['spam_seconds'])]
        messages.append(current_time)
        spam_data[user_id]["messages"] = messages
        
        if len(messages) > int(config['AntiSpam']['max_messages']):
            await message.delete()
            if user_id not in user_data:
                user_data[user_id] = {"warns": 0}
            user_data[user_id]["warns"] += 1
            warns_count = user_data[user_id]["warns"]
            
            mute_duration = timedelta(minutes=int(config['AntiSpam']['mute_minutes']))
            until_date = current_time + mute_duration
            
            await bot.restrict_chat_member(
                message.chat.id,
                user_id,
                permissions=types.ChatPermissions(can_send_messages=False),
                until_date=until_date
            )
            
            punishment_system.add_punishment('mutes', {
                "user_id": user_id,
                "admin_id": bot.id,
                "admin_name": "Система антиспам",
                "reason": "Флуд сообщениями",
                "until_date": until_date.timestamp(),
                "date": current_time.timestamp()
            })
            
            response = f"""
{DECORATIONS['header']}
{EMOJIS['alert']} **ОБНАРУЖЕН СПАМ** {EMOJIS['alert']}
{DECORATIONS['separator']}

{EMOJIS['guard']} *Нарушитель:* {message.from_user.get_mention()}
{EMOJIS['scroll']} *Наказание:* Варн + Мут {config['AntiSpam']['mute_minutes']} минут
{EMOJIS['alert']} *Варнов:* {warns_count}/3

{DECORATIONS['footer']}
"""
            await message.answer(response, parse_mode="Markdown")

    # Проверка на накопленные варны
    if user_id in user_data and user_data[user_id]["warns"] >= 3:
        mute_duration = timedelta(hours=3)
        until_date = current_time + mute_duration
        
        await bot.restrict_chat_member(
            message.chat.id,
            user_id,
            permissions=types.ChatPermissions(can_send_messages=False),
            until_date=until_date
        )
        
        punishment_system.add_punishment('mutes', {
            "user_id": user_id,
            "admin_id": bot.id,
            "admin_name": "Система варнов",
            "reason": "Превышен лимит предупреждений (3/3)",
            "until_date": until_date.timestamp(),
            "date": current_time.timestamp()
        })
        
        response = f"""
{DECORATIONS['header']}
{EMOJIS['mute']} **АВТОМАТИЧЕСКИЙ МУТ** {EMOJIS['mute']}
{DECORATIONS['separator']}

{EMOJIS['guard']} *Нарушитель:* {message.from_user.get_mention()}
{EMOJIS['time']} *Срок:* 3 часа
{EMOJIS['scroll']} *Причина:* Превышен лимит предупреждений (3/3)

{DECORATIONS['footer']}
"""
        await message.answer(response, parse_mode="Markdown")
        user_data[user_id]["warns"] = 0

# Запуск бота
async def on_startup(dp):
    await punishment_system.check_expired_punishments(bot)
    logging.info("Bot started and punishments checked")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)

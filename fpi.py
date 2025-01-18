import asyncio
import aiohttp
from datetime import datetime, timedelta
import configparser
import os
from aiogram import Bot, Dispatcher, types
from aiogram.dispatcher.handler import CancelHandler
from aiogram.dispatcher.middlewares import BaseMiddleware
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ChatPermissions
import time
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot_log.txt'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

START_TIME = datetime.now()

class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, limit=3, timeout=3):
        self.limit = limit
        self.timeout = timeout
        self.user_timeouts = {}
        super(ThrottlingMiddleware, self).__init__()

    async def on_process_message(self, message: types.Message, _):
        user_id = message.from_user.id
        current_time = time.time()
        
        if user_id not in self.user_timeouts:
            self.user_timeouts[user_id] = []
        
        self.user_timeouts[user_id] = [t for t in self.user_timeouts[user_id] 
                                     if current_time - t < self.timeout]
        
        if len(self.user_timeouts[user_id]) >= self.limit:
            remaining_time = round(self.timeout - (current_time - self.user_timeouts[user_id][0]))
            await message.answer(
                f"⚠️ *Флуд-контроль активирован!*\n"
                f"Подождите {remaining_time} секунд перед следующей командой.",
                parse_mode="Markdown"
            )
            raise CancelHandler()
        
        self.user_timeouts[user_id].append(current_time)

class Config:
    def __init__(self, filename='config.ini'):
        self.filename = filename
        self.config = configparser.ConfigParser()
        self.load_config()

    def load_config(self):
        if os.path.exists(self.filename):
            self.config.read(self.filename)
        self.init_default_config()

    def init_default_config(self):
        if 'Bot' not in self.config:
            self.config['Bot'] = {'token': 'YOUR_BOT_TOKEN'}
        if 'Admin' not in self.config:
            self.config['Admin'] = {'admin_ids': '123456789'}
        if 'Chat' not in self.config:
            self.config['Chat'] = {'main_chat_id': '-1001234567890'}
        if 'Stats' not in self.config:
            self.config['Stats'] = {
                'total_users': '0',
                'coin_requests': '0',
                'daily_activity': '0',
                'unique_users': '[]'
            }
        self.save_config()

    def save_config(self):
        with open(self.filename, 'w') as configfile:
            self.config.write(configfile)

    def update_stats(self, user_id, command=None):
        if 'Stats' not in self.config:
            self.config['Stats'] = {}
        
        users = eval(self.config['Stats'].get('unique_users', '[]'))
        if user_id not in users:
            users.append(user_id)
            self.config['Stats']['unique_users'] = str(users)
            self.config['Stats']['total_users'] = str(len(users))

        if command == '/coin':
            coin_requests = int(self.config['Stats'].get('coin_requests', 0))
            self.config['Stats']['coin_requests'] = str(coin_requests + 1)

        daily_activity = int(self.config['Stats'].get('daily_activity', 0))
        self.config['Stats']['daily_activity'] = str(daily_activity + 1)
        
        self.save_config()

    def reset_daily_stats(self):
        self.config['Stats']['daily_activity'] = '0'
        self.save_config()

    def get_system_stats(self):
        try:
            # CPU
            cpu_usage = 0
            try:
                with open('/sys/class/thermal/thermal_zone0/temp') as f:
                    cpu_temp = float(f.read().strip()) / 1000
                    cpu_usage = cpu_temp
            except:
                pass

            # RAM
            ram_usage = 0
            try:
                with open('/proc/meminfo') as f:
                    lines = f.readlines()
                    total = int(lines[0].split()[1])
                    available = int(lines[2].split()[1])
                    ram_usage = round(((total - available) / total) * 100, 2)
            except:
                pass

            return round(cpu_usage, 2), round(ram_usage, 2)
        except:
            return 0, 0

config = Config()
bot = Bot(token=config.config['Bot']['token'])
dp = Dispatcher(bot)
dp.middleware.setup(ThrottlingMiddleware())

timeframes_kb = InlineKeyboardMarkup(row_width=3)
timeframes_kb.add(
    InlineKeyboardButton('5M 📊', callback_data='tf_5m'),
    InlineKeyboardButton('30M 📈', callback_data='tf_30m'),
    InlineKeyboardButton('1H 📉', callback_data='tf_1h'),
    InlineKeyboardButton('1D 💹', callback_data='tf_1d'),
    InlineKeyboardButton('ALL 📊', callback_data='tf_all')
)

@dp.message_handler(commands=['start'])
async def send_welcome(message: types.Message):
    try:
        config.update_stats(message.from_user.id)
        welcome_text = (
            "👋 *Добро пожаловать в FPIBANK!*\n\n"
            "🤖 Я ваш персональный помощник.\n"
            "📊 Используйте /coin чтобы узнать текущий курс\n"
            "ℹ️ /about - информация о создателе\n"
            "📢 /all - пингануть всех участников (только для админов)\n"
            "👥 /mod - пингануть админов (только для админов)"
        )
        await message.answer(welcome_text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in welcome command: {e}")

@dp.message_handler(commands=['about'])
async def show_about(message: types.Message):
    try:
        about_text = (
            "👨‍💻 *Creator:* Нектор\n"
            "📱 *Contact:* @purplekiller\n"
            "🌟 ай ай ай эщкере 1488"
        )
        await message.answer(about_text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in about command: {e}")

@dp.message_handler(commands=['stat'])
async def show_stats(message: types.Message):
    try:
        if str(message.from_user.id) not in config.config['Admin']['admin_ids'].split(','):
            return
        
        cpu_usage, ram_usage = config.get_system_stats()
        uptime = datetime.now() - START_TIME
        hours = uptime.total_seconds() // 3600
        minutes = (uptime.total_seconds() % 3600) // 60
        
        stats_message = (
            "📊 *Статистика бота*\n\n"
            "*💻 Система:*\n"
            f"🔄 CPU: {cpu_usage}%\n"
            f"💾 RAM: {ram_usage}%\n"
            f"⏱ Время работы: {int(hours)}ч {int(minutes)}м\n\n"
            "*👥 Пользователи:*\n"
            f"📈 Всего пользователей: {config.config['Stats']['total_users']}\n"
            f"🔄 Использований /coin: {config.config['Stats']['coin_requests']}\n"
            f"📊 Активность сегодня: {config.config['Stats']['daily_activity']} команд\n"
        )
        
        await message.answer(stats_message, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error in stat command: {e}")

async def get_pair_data():
    pair_address = 'eqayrrajgsuyhrggo1himnbgv9tvlndz3uoclaoytw_fgegd'
    url = f'https://api.dexscreener.com/latest/dex/pairs/ton/{pair_address}'
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.json()

@dp.message_handler(commands=['coin'])
async def show_coin_info(message: types.Message):
    try:
        config.update_stats(message.from_user.id, '/coin')
        
        data = await get_pair_data()
        pair_data = data['pairs'][0]
        
        price = float(pair_data['priceUsd'])
        price_change_24h = float(pair_data['priceChange']['h24'])
        market_cap = float(pair_data.get('fdv', 0))
        liquidity = float(pair_data.get('liquidity', {}).get('usd', 0))
        volume_24h = float(pair_data.get('volume', {}).get('h24', 0))
        
        trend = "📈 Растёт" if price_change_24h > 0 else "📉 Падает"
        current_time = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        
        message_text = (
            "🏦 *FPIBANK Price Analysis*\n\n"
            f"💰 Цена: ${price:.6f}\n"
            f"📊 24h: {price_change_24h:+.2f}%\n"
            f"📈 Тренд: {trend}\n\n"
            f"📊 *Рыночные данные:*\n"
            f"💎 Market Cap: ${market_cap:,.2f}\n"
            f"💧 Ликвидность: ${liquidity:,.2f}\n"
            f"📈 Объём (24h): ${volume_24h:,.2f}\n\n"
            f"🕒 {current_time}"
        )

        await message.answer(
            message_text,
            parse_mode="Markdown",
            reply_markup=timeframes_kb
        )
        
    except Exception as e:
        logger.error(f"Error in coin command: {e}")
        error_message = "❌ *Ошибка при получении данных*\n\nПожалуйста, попробуйте позже или обратитесь к администратору."
        await message.answer(error_message, parse_mode="Markdown")

@dp.callback_query_handler(lambda c: c.data.startswith('tf_'))
async def process_timeframe(callback_query: types.CallbackQuery):
    try:
        timeframe = callback_query.data.split('_')[1]
        
        data = await get_pair_data()
        pair_data = data['pairs'][0]
        
        timeframe_text = {
            '5m': '5 минут',
            '30m': '30 минут',
            '1h': '1 час',
            '1d': '24 часа',
            'all': 'всё время'
        }
        
        price_changes = {
            '5m': pair_data['priceChange'].get('m5', 0),
            '30m': pair_data['priceChange'].get('m30', 0),
            '1h': pair_data['priceChange'].get('h1', 0),
            '1d': pair_data['priceChange'].get('h24', 0),
            'all': pair_data['priceChange'].get('h24', 0)
        }
        
        price = float(pair_data['priceUsd'])
        change = price_changes[timeframe]
        
        trend = "📈 Растёт" if float(change) > 0 else "📉 Падает"
        
        message_text = (
            f"🏦 *FPIBANK - Анализ за {timeframe_text[timeframe]}*\n\n"
            f"💰 Текущая цена: ${price:.6f}\n"
            f"📊 Изменение: {change:+.2f}%\n"
            f"📈 Тренд: {trend}\n\n"
            f"🕒 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}"
        )
        
        await callback_query.message.edit_text(
            message_text,
            parse_mode="Markdown",
            reply_markup=timeframes_kb
        )
        
    except Exception as e:
        logger.error(f"Error in timeframe callback: {e}")
        await callback_query.message.edit_text(
            "❌ Ошибка при получении данных. Попробуйте позже.",
            reply_markup=timeframes_kb
        )

    await callback_query.answer()

@dp.message_handler(commands=['all'])
async def ping_all(message: types.Message):
    try:
        if str(message.chat.id) != config.config['Chat']['main_chat_id']:
            return
            
        member = await message.chat.get_member(message.from_user.id)
        if member.status not in ['creator', 'administrator']:
            await message.reply(
                "❌ *Ошибка доступа*\n"
                "Эта команда доступна только администраторам!",
                parse_mode="Markdown"
            )
            return

        status_msg = await message.answer("🔄 *Собираю список участников...*", parse_mode="Markdown")
        
        try:
            members = []
            async for member in message.chat.get_members():
                if not member.user.is_bot:
                    members.append(member.user)

            if len(members) > 0:
                tags = []
                for member in members:
                    tag = f"[{member.first_name}](tg://user?id={member.id})"
                    tags.append(tag)
                    if len(' '.join(tags)) > 3500:
                        await message.answer(
                            "📢 *Внимание!*\n\n" + ' '.join(tags),
                            parse_mode="Markdown"
                        )
                        tags = []
                if tags:
                    await message.answer(
                        "📢 *Внимание!*\n\n" + ' '.join(tags),
                        parse_mode="Markdown"
                    )
                await status_msg.delete()
            else:
                await status_msg.edit_text(
                    "❌ *Ошибка*\n"
                    "Не удалось получить список участников!",
                    parse_mode="Markdown"
                )
        except Exception as e:
            logger.error(f"Error in ping_all: {e}")
            await status_msg.edit_text(
                "❌ *Ошибка*\n"
                "Произошла ошибка при получении списка участников!",
                parse_mode="Markdown"
            )

    except Exception as e:
        logger.error(f"Error in ping_all (outer): {e}")
        await message.reply(
            "❌ *Системная ошибка*\n"
            "Произошла ошибка при выполнении команды!",
            parse_mode="Markdown"
        )

@dp.message_handler(commands=['mod'])
async def ping_mods(message: types.Message):
    try:
        if str(message.chat.id) != config.config['Chat']['main_chat_id']:
            return
            
        member = await message.chat.get_member(message.from_user.id)
        if member.status not in ['creator', 'administrator']:
            await message.reply(
                "❌ *Ошибка доступа*\n"
                "Эта команда доступна только администраторам!",
                parse_mode="Markdown"
            )
            return

        status_msg = await message.answer("🔄 *Собираю список администраторов...*", parse_mode="Markdown")
        
        try:
            admins = []
            async for member in message.chat.get_members(filter="administrators"):
                if not member.user.is_bot:
                    admins.append(member.user)

            if len(admins) > 0:
                tags = []
                for admin in admins:
                    tag = f"[{admin.first_name}](tg://user?id={admin.id})"
                    tags.append(tag)
                await status_msg.edit_text(
                    "👥 *Внимание, администраторы!*\n\n" + ' '.join(tags),
                    parse_mode="Markdown"
                )
            else:
                await status_msg.edit_text(
                    "❌ *Ошибка*\n"
                    "Не удалось получить список администраторов!",
                    parse_mode="Markdown"
                )
        except Exception as e:
            logger.error(f"Error in ping_mods: {e}")
            await status_msg.edit_text(
                "❌ *Ошибка*\n"
                "Произошла ошибка при получении списка администраторов!",
                parse_mode="Markdown"
            )

    except Exception as e:
        logger.error(f"Error in ping_mods (outer): {e}")
        await message.reply(
            "❌ *Системная ошибка*\n"
            "Произошла ошибка при выполнении команды!",
            parse_mode="Markdown"
        )

@dp.message_handler(content_types=['new_chat_members'])
async def welcome_new_member(message: types.Message):
    try:
        if str(message.chat.id) != config.config['Chat']['main_chat_id']:
            return
            
        for new_member in message.new_chat_members:
            if not new_member.is_bot:
                welcome_text = (
                    "🌟 Добро пожаловать в чат FPI-Клан!\n\n"
                    "🤖 У нас есть собственный бот: @Fpiclan_bot\n\n"
                    "👥 Нам требуются:\n"
                    "• 📣 Рекламщики\n"
                    "• 💡 Идеи для сайта\n"
                    "• 🎨 Дизайнеры для картинок сайта"
                )
                await message.answer(welcome_text)

    except Exception as e:
        logger.error(f"Error in welcome message: {e}")

async def reset_daily_stats():
    while True:
        try:
            now = datetime.now()
            next_day = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            if now >= next_day:
                next_day = next_day.replace(day=next_day.day + 1)
            await asyncio.sleep((next_day - now).seconds)
            config.reset_daily_stats()
        except Exception as e:
            logger.error(f"Error in reset_daily_stats: {e}")
            await asyncio.sleep(60)

if __name__ == '__main__':
    from aiogram import executor
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.create_task(reset_daily_stats())
        executor.start_polling(dp, skip_updates=True)
    except Exception as e:
        logger.error(f"Main loop error: {e}")

import discord
from discord.ext import commands
import os
import aiosqlite
from dotenv import load_dotenv

# Завантаження змінних оточення з файлу .env
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
PREFIX = os.getenv("COMMAND_PREFIX", "!")

# Налаштування intents (намірів) для отримання подій від Discord
intents = discord.Intents.default()
intents.message_content = True # Необхідно для зчитування тексту повідомлень
intents.members = True         # Необхідно для керування учасниками (модерація)
# Додаємо наміри для модерації і аудит логів
intents.moderation = True
intents.guilds = True

class ServerManagementBot(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=PREFIX,
            intents=intents,
        )

    async def setup_hook(self):
        # Підключення до бази даних SQLite
        self.db = await aiosqlite.connect('bot.db')
        
        # Створення таблиць
        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER,
                guild_id INTEGER,
                xp INTEGER DEFAULT 0,
                level INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, guild_id)
            )
        ''')
        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                guild_id INTEGER,
                moderator_id INTEGER,
                reason TEXT,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS shop_items (
                id TEXT,
                guild_id INTEGER,
                name TEXT,
                price INTEGER,
                role_name TEXT,
                PRIMARY KEY (id, guild_id)
            )
        ''')
        
        # Міграція: додаємо колонку balance до таблиці users, якщо її ще немає
        try:
            await self.db.execute('ALTER TABLE users ADD COLUMN balance INTEGER DEFAULT 0')
        except Exception:
            pass
        # Міграція: кулдауни економіки (зберігаються між перезапусками)
        try:
            await self.db.execute('ALTER TABLE users ADD COLUMN last_work INTEGER DEFAULT 0')
        except Exception:
            pass
        try:
            await self.db.execute('ALTER TABLE users ADD COLUMN last_daily INTEGER DEFAULT 0')
        except Exception:
            pass

        # Таблиця заборонених слів (0 = глобальні, guild_id = для конкретного серверу)
        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS banned_words (
                word TEXT,
                guild_id INTEGER,
                PRIMARY KEY (word, guild_id)
            )
        ''')

        # Таблиця каналів де фільтр вимкнено
        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS automod_excluded_channels (
                channel_id INTEGER,
                guild_id INTEGER,
                PRIMARY KEY (channel_id, guild_id)
            )
        ''')

        # Таблиця білого списку слів (whitelist)
        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS whitelisted_words (
                word TEXT,
                guild_id INTEGER,
                PRIMARY KEY (word, guild_id)
            )
        ''')

        # === Нові таблиці для статистики активності (Голос/Текст) ===
        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS voice_stats (
                user_id INTEGER,
                guild_id INTEGER,
                channel_id INTEGER,
                total_time INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, guild_id, channel_id)
            )
        ''')

        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS text_stats (
                user_id INTEGER,
                guild_id INTEGER,
                words_week INTEGER DEFAULT 0,
                words_month INTEGER DEFAULT 0,
                words_year INTEGER DEFAULT 0,
                words_total INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, guild_id)
            )
        ''')

        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS user_privacy (
                user_id INTEGER,
                guild_id INTEGER,
                show_voice BOOLEAN DEFAULT 1,
                show_text BOOLEAN DEFAULT 1,
                show_favorite_channel BOOLEAN DEFAULT 1,
                PRIMARY KEY (user_id, guild_id)
            )
        ''')

        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS server_settings (
                guild_id INTEGER PRIMARY KEY,
                summary_channel_id INTEGER,
                ai_summary_enabled BOOLEAN DEFAULT 0,
                voice_xp_enabled BOOLEAN DEFAULT 1,
                dynamic_roles_enabled BOOLEAN DEFAULT 0,
                anti_afk_enabled BOOLEAN DEFAULT 1,
                speaker_role_id INTEGER,
                writer_role_id INTEGER,
                command_channel_id INTEGER,
                last_weekly_reset TIMESTAMP,
                last_monthly_reset TIMESTAMP,
                last_yearly_reset TIMESTAMP
            )
        ''')

        # Міграція для server_settings (якщо таблиця вже існує)
        for col, default in [
            ("ai_summary_enabled", "0"),
            ("voice_xp_enabled", "1"),
            ("dynamic_roles_enabled", "0"),
            ("anti_afk_enabled", "1"),
            ("speaker_role_id", "NULL"),
            ("writer_role_id", "NULL"),
            ("command_channel_id", "NULL")
        ]:
            try:
                await self.db.execute(f'ALTER TABLE server_settings ADD COLUMN {col} INTEGER DEFAULT {default}')
            except Exception:
                pass

        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS achievements (
                user_id INTEGER,
                guild_id INTEGER,
                achievement_id TEXT,
                date_earned TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, guild_id, achievement_id)
            )
        ''')

        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS level_roles (
                guild_id INTEGER,
                level INTEGER,
                add_role_id INTEGER,
                remove_role_id INTEGER,
                PRIMARY KEY (guild_id, level)
            )
        ''')

        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS voice_activity_stats (
                user_id INTEGER,
                guild_id INTEGER,
                time_week INTEGER DEFAULT 0,
                time_month INTEGER DEFAULT 0,
                time_year INTEGER DEFAULT 0,
                time_total INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, guild_id)
            )
        ''')

        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS music_queues (
                user_id INTEGER,
                guild_id INTEGER,
                url TEXT,
                title TEXT,
                pos INTEGER,
                PRIMARY KEY (user_id, guild_id, pos)
            )
        ''')

        await self.db.execute('''
            CREATE TABLE IF NOT EXISTS music_current_playback (
                guild_id INTEGER PRIMARY KEY,
                channel_id INTEGER,
                url TEXT,
                title TEXT,
                position REAL,
                requester_id INTEGER,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        await self.db.commit()

        # Автоматичне завантаження всіх cogs (модулів) з папки cogs
        if not os.path.exists('./cogs'):
            os.makedirs('./cogs')
            
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py') and not filename.startswith('__'):
                try:
                    await self.load_extension(f'cogs.{filename[:-3]}')
                    print(f"✅ Завантажено модуль: {filename}")
                except Exception as e:
                    print(f"❌ Помилка завантаження {filename}: {e}")
        
        # Синхронізація команд (slash commands)
        try:
            await self.tree.sync()
            print("🔄 Командне дерево синхронізовано.")
        except Exception as e:
            print(f"⚠️ Помилка синхронізації команд: {e}")

    async def close(self):
        if hasattr(self, 'db'):
            await self.db.close()
            print("💾 Відключено від бази даних.")
        await super().close()

    async def on_ready(self):
        print(f'🤖 Увійшли як {self.user} (ID: {self.user.id})')
        print('-------------------------------------------')
        # Встановлення статусу бота
        await self.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="на сервер"))

    # Таблиця: Кирилиця -> Латиниця (QWERTY Ukrainian layout)
    CYRMAP = str.maketrans({
        'й':'q','ц':'w','у':'e','к':'r','е':'t','н':'y','г':'u','ш':'i','щ':'o','з':'p',
        'ф':'a','і':'s','в':'d','а':'f','п':'g','р':'h','о':'j','л':'k','д':'l',
        'я':'z','ч':'x','с':'c','м':'v','и':'b','т':'n','ь':'m',
        'Й':'Q','Ц':'W','У':'E','К':'R','Е':'T','Н':'Y','Г':'U','Ш':'I','Щ':'O','З':'P',
        'Ф':'A','І':'S','В':'D','А':'F','П':'G','Р':'H','О':'J','Л':'K','Д':'L',
        'Я':'Z','Ч':'X','С':'C','М':'V','И':'B','Т':'N','Ь':'M',
    })

    async def on_message(self, message):
        if message.author.bot:
            await self.process_commands(message)
            return

        content = message.content
        # Якщо команда з кириличними символами — транслітеруємо назву команди
        if content.startswith(PREFIX):
            after_prefix = content[len(PREFIX):]
            parts = after_prefix.split(None, 1)
            if parts:
                cmd_word = parts[0]
                if any('\u0400' <= c <= '\u04ff' for c in cmd_word):
                    latin_cmd = cmd_word.translate(self.CYRMAP)
                    rest = (' ' + parts[1]) if len(parts) > 1 else ''
                    new_content = f"{PREFIX}{latin_cmd}{rest}"
                    # Замінюємо content напряму — discord.py читає message.content
                    message.content = new_content

        await self.process_commands(message)

bot = ServerManagementBot()

@bot.check
async def global_command_channel_check(ctx):
    # Дозволяємо в ПП
    if not ctx.guild:
        return True

    # Музичні команди мають своє власне обмеження (лише голосові канали)
    music_commands = ["join", "play", "skip", "pause", "resume", "queue", "history", "cq", "volume", "stop"]
    
    # getattr безпечний, якщо ctx.command == None (що буває, якщо команда не знайдена)
    cmd_name = getattr(ctx.command, "name", "")
    if cmd_name in music_commands:
        return True

    async with bot.db.execute('SELECT command_channel_id FROM server_settings WHERE guild_id = ?', (ctx.guild.id,)) as cursor:
        row = await cursor.fetchone()

    if row and row[0]:
        cmd_channel_id = row[0]
        # set_command_channel - це слеш-команда, але на всяк випадок перевірку на ім'я залишаємо
        if ctx.channel.id != cmd_channel_id:
            try:
                await ctx.message.delete(delay=0)
            except Exception:
                pass
            await ctx.send(f"❌ Команди бота можна використовувати лише в <#{cmd_channel_id}>.", delete_after=5)
            # Повертаємо False щоб скасувати виконання команди
            return False

    return True

if __name__ == '__main__':
    if not TOKEN or TOKEN == "your_bot_token_here":
        print("Помилка: Не знайдено правильний DISCORD_TOKEN. Додайте його в файл .env")
    else:
        bot.run(TOKEN)
